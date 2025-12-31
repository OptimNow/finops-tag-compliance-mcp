"""Tag suggestion service for intelligent tag recommendations."""

import re
import logging
from typing import Optional

from ..models import TagSuggestion
from ..services.policy_service import PolicyService


logger = logging.getLogger(__name__)


class SuggestionService:
    """
    Service for generating intelligent tag suggestions for AWS resources.
    
    Analyzes resource metadata and patterns to suggest appropriate tag values:
    - VPC/subnet naming patterns
    - IAM user/role patterns
    - Similar tagged resources
    - Resource naming conventions
    
    Requirements: 5.1, 5.2, 5.3, 5.4
    """
    
    # Environment patterns for detection
    ENVIRONMENT_PATTERNS = {
        "production": [
            r"prod", r"prd", r"production", r"live", r"main"
        ],
        "staging": [
            r"stag", r"stg", r"staging", r"preprod", r"pre-prod", r"uat"
        ],
        "development": [
            r"dev", r"develop", r"development", r"sandbox"
        ],
        "test": [
            r"test", r"tst", r"qa", r"quality"
        ]
    }
    
    # Cost center patterns based on common naming conventions
    COST_CENTER_PATTERNS = {
        "Engineering": [
            r"eng", r"engineering", r"tech", r"platform", r"infra", r"backend", r"frontend", r"devops", r"sre"
        ],
        "Marketing": [
            r"mkt", r"marketing", r"campaign", r"analytics", r"growth"
        ],
        "Sales": [
            r"sales", r"crm", r"revenue", r"commercial"
        ],
        "Operations": [
            r"ops", r"operations", r"support", r"helpdesk", r"service"
        ],
        "Finance": [
            r"fin", r"finance", r"billing", r"accounting", r"payment"
        ]
    }
    
    # Data classification patterns
    DATA_CLASSIFICATION_PATTERNS = {
        "public": [
            r"public", r"cdn", r"static", r"assets", r"media"
        ],
        "internal": [
            r"internal", r"private", r"corp", r"intranet"
        ],
        "confidential": [
            r"confidential", r"sensitive", r"pii", r"customer"
        ],
        "restricted": [
            r"restricted", r"secret", r"classified", r"hipaa", r"pci"
        ]
    }
    
    # Confidence score constants for pattern matching
    CONFIDENCE_VPC_NAME = 0.85
    CONFIDENCE_IAM_ROLE = 0.80
    CONFIDENCE_RESOURCE_NAME = 0.75
    CONFIDENCE_RESOURCE_ARN = 0.65
    CONFIDENCE_DEFAULT = 0.50
    
    def __init__(self, policy_service: PolicyService):
        """
        Initialize the SuggestionService.
        
        Args:
            policy_service: PolicyService for accessing tag policy configuration
        """
        self.policy_service = policy_service
    
    async def suggest_tags(
        self,
        resource_arn: str,
        resource_type: str,
        resource_name: str,
        current_tags: dict[str, str],
        vpc_name: Optional[str] = None,
        iam_role: Optional[str] = None,
        similar_resources: Optional[list[dict]] = None
    ) -> list[TagSuggestion]:
        """
        Generate tag suggestions for a resource.
        
        Analyzes resource metadata and patterns to suggest appropriate tag values.
        Each suggestion includes a confidence score and reasoning.
        
        Args:
            resource_arn: ARN of the resource
            resource_type: Type of resource (e.g., "ec2:instance")
            resource_name: Name or identifier of the resource
            current_tags: Current tags on the resource
            vpc_name: Optional VPC name for context
            iam_role: Optional IAM role name for context
            similar_resources: Optional list of similar resources with their tags
        
        Returns:
            List of TagSuggestion objects with confidence scores and reasoning
        
        Requirements: 5.1, 5.2, 5.3, 5.4
        """
        suggestions = []
        
        # Get required tags for this resource type
        required_tags = self.policy_service.get_required_tags(resource_type)
        
        # Build context from all available information
        context = self._build_context(
            resource_arn=resource_arn,
            resource_name=resource_name,
            vpc_name=vpc_name,
            iam_role=iam_role
        )
        
        # Generate suggestions for each missing required tag
        for tag in required_tags:
            tag_name = tag.name
            
            # Skip if tag already exists
            if tag_name in current_tags:
                continue
            
            # Try different suggestion strategies
            suggestion = await self._suggest_tag_value(
                tag_name=tag_name,
                allowed_values=tag.allowed_values,
                validation_regex=tag.validation_regex,
                context=context,
                similar_resources=similar_resources
            )
            
            if suggestion:
                suggestions.append(suggestion)
        
        return suggestions
    
    def _build_context(
        self,
        resource_arn: str,
        resource_name: str,
        vpc_name: Optional[str],
        iam_role: Optional[str]
    ) -> dict[str, str]:
        """
        Build a context dictionary from all available resource information.
        
        Args:
            resource_arn: ARN of the resource
            resource_name: Name or identifier of the resource
            vpc_name: Optional VPC name
            iam_role: Optional IAM role name
        
        Returns:
            Dictionary with normalized context strings for pattern matching
        """
        context = {
            "arn": resource_arn.lower() if resource_arn else "",
            "name": resource_name.lower() if resource_name else "",
            "vpc": vpc_name.lower() if vpc_name else "",
            "iam_role": iam_role.lower() if iam_role else ""
        }
        
        # Combine all context into a single searchable string
        context["combined"] = " ".join(filter(None, context.values()))
        
        return context
    
    async def _suggest_tag_value(
        self,
        tag_name: str,
        allowed_values: Optional[list[str]],
        validation_regex: Optional[str],
        context: dict[str, str],
        similar_resources: Optional[list[dict]]
    ) -> Optional[TagSuggestion]:
        """
        Suggest a value for a specific tag.
        
        Uses multiple strategies:
        1. Pattern matching against context
        2. Similar resource analysis
        3. Default value inference
        
        Args:
            tag_name: Name of the tag to suggest
            allowed_values: List of allowed values (if constrained)
            validation_regex: Regex pattern for validation (if any)
            context: Context dictionary for pattern matching
            similar_resources: List of similar resources with their tags
        
        Returns:
            TagSuggestion if a suggestion can be made, None otherwise
        """
        # Strategy 1: Pattern-based suggestion
        pattern_suggestion = self._suggest_from_patterns(
            tag_name=tag_name,
            allowed_values=allowed_values,
            context=context
        )
        
        if pattern_suggestion:
            return pattern_suggestion
        
        # Strategy 2: Similar resource analysis
        if similar_resources:
            similar_suggestion = self._suggest_from_similar_resources(
                tag_name=tag_name,
                allowed_values=allowed_values,
                similar_resources=similar_resources
            )
            
            if similar_suggestion:
                return similar_suggestion
        
        # Strategy 3: Context-based inference for specific tags
        inference_suggestion = self._suggest_from_inference(
            tag_name=tag_name,
            allowed_values=allowed_values,
            validation_regex=validation_regex,
            context=context
        )
        
        if inference_suggestion:
            return inference_suggestion
        
        return None
    
    def _suggest_from_patterns(
        self,
        tag_name: str,
        allowed_values: Optional[list[str]],
        context: dict[str, str]
    ) -> Optional[TagSuggestion]:
        """
        Suggest tag value based on pattern matching.
        
        Analyzes VPC names, resource names, and IAM roles for patterns
        that indicate appropriate tag values.
        
        Args:
            tag_name: Name of the tag
            allowed_values: List of allowed values
            context: Context dictionary
        
        Returns:
            TagSuggestion if pattern match found, None otherwise
        
        Requirements: 5.4 - Base suggestions on VPC naming, IAM user/role patterns
        """
        combined_context = context.get("combined", "")
        
        if tag_name == "Environment":
            return self._match_environment_pattern(combined_context, context)
        
        elif tag_name == "CostCenter":
            return self._match_cost_center_pattern(combined_context, context)
        
        elif tag_name == "DataClassification":
            return self._match_data_classification_pattern(combined_context, context)
        
        return None
    
    def _match_environment_pattern(
        self,
        combined_context: str,
        context: dict[str, str]
    ) -> Optional[TagSuggestion]:
        """
        Match environment patterns in context.
        
        Args:
            combined_context: Combined context string
            context: Full context dictionary
        
        Returns:
            TagSuggestion for Environment tag if pattern found
        """
        for env_value, patterns in self.ENVIRONMENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined_context, re.IGNORECASE):
                    # Determine confidence based on where the match was found
                    confidence, source = self._calculate_pattern_confidence(
                        pattern, context
                    )
                    
                    return TagSuggestion(
                        tag_key="Environment",
                        suggested_value=env_value,
                        confidence=confidence,
                        reasoning=f"Detected '{pattern}' pattern in {source}, suggesting {env_value} environment"
                    )
        
        return None
    
    def _match_cost_center_pattern(
        self,
        combined_context: str,
        context: dict[str, str]
    ) -> Optional[TagSuggestion]:
        """
        Match cost center patterns in context.
        
        Args:
            combined_context: Combined context string
            context: Full context dictionary
        
        Returns:
            TagSuggestion for CostCenter tag if pattern found
        """
        for cost_center, patterns in self.COST_CENTER_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined_context, re.IGNORECASE):
                    confidence, source = self._calculate_pattern_confidence(
                        pattern, context
                    )
                    
                    return TagSuggestion(
                        tag_key="CostCenter",
                        suggested_value=cost_center,
                        confidence=confidence,
                        reasoning=f"Detected '{pattern}' pattern in {source}, suggesting {cost_center} cost center"
                    )
        
        return None
    
    def _match_data_classification_pattern(
        self,
        combined_context: str,
        context: dict[str, str]
    ) -> Optional[TagSuggestion]:
        """
        Match data classification patterns in context.
        
        Args:
            combined_context: Combined context string
            context: Full context dictionary
        
        Returns:
            TagSuggestion for DataClassification tag if pattern found
        """
        for classification, patterns in self.DATA_CLASSIFICATION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined_context, re.IGNORECASE):
                    confidence, source = self._calculate_pattern_confidence(
                        pattern, context
                    )
                    
                    return TagSuggestion(
                        tag_key="DataClassification",
                        suggested_value=classification,
                        confidence=confidence,
                        reasoning=f"Detected '{pattern}' pattern in {source}, suggesting {classification} classification"
                    )
        
        return None
    
    def _calculate_pattern_confidence(
        self,
        pattern: str,
        context: dict[str, str]
    ) -> tuple[float, str]:
        """
        Calculate confidence score based on where pattern was found.
        
        Higher confidence for matches in more specific contexts:
        - VPC name: 0.85 (very reliable indicator)
        - IAM role: 0.80 (reliable indicator)
        - Resource name: 0.75 (good indicator)
        - ARN: 0.65 (moderate indicator)
        
        Args:
            pattern: The pattern that matched
            context: Context dictionary
        
        Returns:
            Tuple of (confidence_score, source_description)
        
        Requirements: 5.2 - Include confidence score (0-1)
        """
        # Check each context source in order of reliability
        if context.get("vpc") and re.search(pattern, context["vpc"], re.IGNORECASE):
            return self.CONFIDENCE_VPC_NAME, "VPC name"
        
        if context.get("iam_role") and re.search(pattern, context["iam_role"], re.IGNORECASE):
            return self.CONFIDENCE_IAM_ROLE, "IAM role"
        
        if context.get("name") and re.search(pattern, context["name"], re.IGNORECASE):
            return self.CONFIDENCE_RESOURCE_NAME, "resource name"
        
        if context.get("arn") and re.search(pattern, context["arn"], re.IGNORECASE):
            return self.CONFIDENCE_RESOURCE_ARN, "resource ARN"
        
        # Default fallback
        return self.CONFIDENCE_DEFAULT, "resource context"
    
    def _suggest_from_similar_resources(
        self,
        tag_name: str,
        allowed_values: Optional[list[str]],
        similar_resources: list[dict]
    ) -> Optional[TagSuggestion]:
        """
        Suggest tag value based on similar resources.
        
        Analyzes tags from similar resources (same VPC, same type, etc.)
        to find common tag values.
        
        Args:
            tag_name: Name of the tag
            allowed_values: List of allowed values
            similar_resources: List of similar resources with their tags
        
        Returns:
            TagSuggestion if common value found, None otherwise
        
        Requirements: 5.4 - Base suggestions on similar resources
        """
        if not similar_resources:
            return None
        
        # Count occurrences of each value for this tag
        value_counts: dict[str, int] = {}
        total_with_tag = 0
        
        for resource in similar_resources:
            tags = resource.get("tags", {})
            if tag_name in tags:
                value = tags[tag_name]
                value_counts[value] = value_counts.get(value, 0) + 1
                total_with_tag += 1
        
        if not value_counts:
            return None
        
        # Find the most common value
        most_common_value = max(value_counts, key=value_counts.get)
        occurrence_count = value_counts[most_common_value]
        
        # Validate against allowed values if specified
        if allowed_values and most_common_value not in allowed_values:
            return None
        
        # Calculate confidence based on consistency
        # Higher confidence if most resources agree on the value
        consistency_ratio = occurrence_count / total_with_tag
        base_confidence = 0.70  # Base confidence for similar resource suggestions
        
        # Adjust confidence based on sample size and consistency
        sample_factor = min(1.0, total_with_tag / 5)  # Max out at 5 similar resources
        confidence = base_confidence * consistency_ratio * sample_factor
        
        # Ensure confidence is within bounds
        confidence = max(0.1, min(0.95, confidence))
        
        return TagSuggestion(
            tag_key=tag_name,
            suggested_value=most_common_value,
            confidence=round(confidence, 2),
            reasoning=f"Found {occurrence_count} of {total_with_tag} similar resources with {tag_name}='{most_common_value}'"
        )
    
    def _suggest_from_inference(
        self,
        tag_name: str,
        allowed_values: Optional[list[str]],
        validation_regex: Optional[str],
        context: dict[str, str]
    ) -> Optional[TagSuggestion]:
        """
        Suggest tag value based on inference from context.
        
        Uses heuristics to infer appropriate values for specific tags
        when pattern matching doesn't find a match.
        
        Args:
            tag_name: Name of the tag
            allowed_values: List of allowed values
            validation_regex: Regex pattern for validation
            context: Context dictionary
        
        Returns:
            TagSuggestion if inference possible, None otherwise
        """
        if tag_name == "Application":
            return self._infer_application_name(context, validation_regex)
        
        elif tag_name == "Owner":
            return self._infer_owner(context, validation_regex)
        
        return None
    
    def _infer_application_name(
        self,
        context: dict[str, str],
        validation_regex: Optional[str]
    ) -> Optional[TagSuggestion]:
        """
        Infer application name from resource name.
        
        Extracts application name from resource naming conventions like:
        - app-name-env-suffix
        - prefix-app-name
        
        Args:
            context: Context dictionary
            validation_regex: Regex pattern for validation
        
        Returns:
            TagSuggestion for Application tag if inference possible
        """
        resource_name = context.get("name", "")
        if not resource_name:
            return None
        
        # Try to extract application name from common patterns
        # Pattern: app-name-env or app-name-region-env
        parts = resource_name.split("-")
        
        if len(parts) >= 2:
            # Remove common suffixes (env names, regions, etc.)
            env_suffixes = {"prod", "prd", "stg", "staging", "dev", "test", "qa"}
            region_patterns = {r"us-east", r"us-west", r"eu-west", r"ap-"}
            
            # Filter out environment and region parts
            app_parts = []
            for part in parts:
                is_env = part.lower() in env_suffixes
                is_region = any(re.search(p, part.lower()) for p in region_patterns)
                is_numeric = part.isdigit()
                
                if not is_env and not is_region and not is_numeric:
                    app_parts.append(part)
            
            if app_parts:
                suggested_name = "-".join(app_parts[:3])  # Limit to 3 parts
                
                # Validate against regex if provided
                if validation_regex:
                    try:
                        if not re.match(validation_regex, suggested_name):
                            # Try to fix common issues
                            suggested_name = suggested_name.lower()
                            if not re.match(validation_regex, suggested_name):
                                return None
                    except re.error:
                        pass
                
                return TagSuggestion(
                    tag_key="Application",
                    suggested_value=suggested_name,
                    confidence=0.60,
                    reasoning=f"Extracted application name '{suggested_name}' from resource name '{resource_name}'"
                )
        
        return None
    
    def _infer_owner(
        self,
        context: dict[str, str],
        validation_regex: Optional[str]
    ) -> Optional[TagSuggestion]:
        """
        Infer owner from IAM role or resource context.
        
        Attempts to extract owner information from IAM role names
        or other context clues.
        
        Args:
            context: Context dictionary
            validation_regex: Regex pattern for validation (usually email format)
        
        Returns:
            TagSuggestion for Owner tag if inference possible
        """
        iam_role = context.get("iam_role", "")
        
        if not iam_role:
            return None
        
        # Try to extract team/owner from IAM role name
        # Common patterns: team-name-role, service-team-role
        parts = iam_role.replace("_", "-").split("-")
        
        # Look for team-like names
        team_keywords = {"team", "squad", "group", "service"}
        
        for i, part in enumerate(parts):
            if part.lower() in team_keywords and i > 0:
                # The part before "team" is likely the team name
                team_name = parts[i - 1]
                
                # Construct a placeholder email
                suggested_email = f"{team_name.lower()}-team@example.com"
                
                # Validate against regex if provided
                if validation_regex:
                    try:
                        if not re.match(validation_regex, suggested_email):
                            return None
                    except re.error:
                        pass
                
                return TagSuggestion(
                    tag_key="Owner",
                    suggested_value=suggested_email,
                    confidence=0.45,
                    reasoning=f"Inferred team '{team_name}' from IAM role '{iam_role}' - please verify email address"
                )
        
        return None
    
    async def suggest_tags_for_resource(
        self,
        resource: dict,
        similar_resources: Optional[list[dict]] = None
    ) -> list[TagSuggestion]:
        """
        Convenience method to suggest tags for a resource dictionary.
        
        Args:
            resource: Resource dictionary with resource_id, resource_type, tags, etc.
            similar_resources: Optional list of similar resources
        
        Returns:
            List of TagSuggestion objects
        """
        return await self.suggest_tags(
            resource_arn=resource.get("arn", resource.get("resource_id", "")),
            resource_type=resource.get("resource_type", ""),
            resource_name=resource.get("resource_id", ""),
            current_tags=resource.get("tags", {}),
            vpc_name=resource.get("vpc_name"),
            iam_role=resource.get("iam_role"),
            similar_resources=similar_resources
        )
