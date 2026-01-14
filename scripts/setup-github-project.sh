#!/bin/bash
# Script pour créer et configurer le GitHub Project pour FinOps Tag Compliance Suite

set -e

# Configuration
ORG="OptimNow"
PROJECT_TITLE="FinOps Tag Compliance Suite"
REPO1="finops-tag-compliance-mcp"
REPO2="tagging-policy-generator"

echo "🚀 Configuration du GitHub Project : $PROJECT_TITLE"
echo "================================================"

# Vérifier que gh CLI est installé
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) n'est pas installé"
    echo "📥 Installez-le : https://cli.github.com/"
    exit 1
fi

# Vérifier l'authentification
echo "🔐 Vérification de l'authentification GitHub..."
if ! gh auth status &> /dev/null; then
    echo "❌ Non authentifié. Lancez: gh auth login"
    exit 1
fi
echo "✅ Authentifié"

# Créer le Project
echo ""
echo "📋 Création du GitHub Project..."
PROJECT_OUTPUT=$(gh project create \
    --owner "$ORG" \
    --title "$PROJECT_TITLE" \
    --format json 2>&1) || {
    echo "❌ Erreur lors de la création du project"
    echo "$PROJECT_OUTPUT"
    exit 1
}

# Extraire le numéro du project
PROJECT_NUMBER=$(echo "$PROJECT_OUTPUT" | jq -r '.number')
PROJECT_URL=$(echo "$PROJECT_OUTPUT" | jq -r '.url')

echo "✅ Project créé : #$PROJECT_NUMBER"
echo "🔗 URL : $PROJECT_URL"

# Lier les repositories
echo ""
echo "🔗 Liaison des repositories au Project..."

echo "  → Liaison de $REPO1..."
gh project link "$PROJECT_NUMBER" \
    --owner "$ORG" \
    --repo "$ORG/$REPO1" || echo "⚠️  Déjà lié ou erreur"

echo "  → Liaison de $REPO2..."
gh project link "$PROJECT_NUMBER" \
    --owner "$ORG" \
    --repo "$ORG/$REPO2" || echo "⚠️  Déjà lié ou erreur"

echo "✅ Repositories liés"

# Créer les champs personnalisés
echo ""
echo "🏷️  Création des champs personnalisés..."

# Note: L'API pour créer des champs personnalisés n'est pas disponible via gh CLI
# Il faut le faire manuellement via l'interface web ou l'API GraphQL
echo "⚠️  Les champs personnalisés doivent être créés manuellement :"
echo ""
echo "1. Allez sur : $PROJECT_URL"
echo "2. Cliquez sur '...' → 'Settings'"
echo "3. Ajoutez ces champs :"
echo ""
echo "   📦 Component (Single Select)"
echo "      - MCP Server"
echo "      - Policy Generator"
echo "      - Integration"
echo "      - Infrastructure"
echo "      - Documentation"
echo ""
echo "   🎯 Priority (Single Select)"
echo "      - High"
echo "      - Medium"
echo "      - Low"
echo ""
echo "   📅 Release (Single Select)"
echo "      - v1.0"
echo "      - v1.1"
echo "      - v2.0"
echo "      - Backlog"
echo ""
echo "   💰 Cost Impact (Single Select)"
echo "      - High"
echo "      - Medium"
echo "      - Low"
echo "      - None"

# Créer des labels recommandés
echo ""
echo "🏷️  Création des labels recommandés..."

create_label() {
    local repo=$1
    local name=$2
    local color=$3
    local description=$4

    gh label create "$name" \
        --repo "$ORG/$repo" \
        --color "$color" \
        --description "$description" \
        --force 2>/dev/null || true
}

# Labels pour MCP Server
echo "  → Labels pour $REPO1..."
create_label "$REPO1" "mcp-server" "0052CC" "MCP Server specific"
create_label "$REPO1" "integration" "5319E7" "Cross-repo integration"
create_label "$REPO1" "priority:high" "D93F0B" "High priority"
create_label "$REPO1" "priority:medium" "FBCA04" "Medium priority"
create_label "$REPO1" "priority:low" "0E8A16" "Low priority"

# Labels pour Policy Generator
echo "  → Labels pour $REPO2..."
create_label "$REPO2" "policy-generator" "1D76DB" "Policy Generator specific"
create_label "$REPO2" "integration" "5319E7" "Cross-repo integration"
create_label "$REPO2" "priority:high" "D93F0B" "High priority"
create_label "$REPO2" "priority:medium" "FBCA04" "Medium priority"
create_label "$REPO2" "priority:low" "0E8A16" "Low priority"

echo "✅ Labels créés"

# Créer un milestone commun
echo ""
echo "📅 Création du milestone v1.0..."

gh api \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    "/repos/$ORG/$REPO1/milestones" \
    -f title='v1.0 - MVP' \
    -f description='Phase 1 MVP with AWS support' \
    -f due_on='2026-03-31T00:00:00Z' \
    2>/dev/null || echo "⚠️  Milestone existe déjà ou erreur"

gh api \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    "/repos/$ORG/$REPO2/milestones" \
    -f title='v1.0 - MVP' \
    -f description='Phase 1 MVP with AWS support' \
    -f due_on='2026-03-31T00:00:00Z' \
    2>/dev/null || echo "⚠️  Milestone existe déjà ou erreur"

echo "✅ Milestones créés"

# Résumé final
echo ""
echo "================================================"
echo "✅ Configuration terminée !"
echo ""
echo "🔗 Project URL : $PROJECT_URL"
echo "📋 Project Number : #$PROJECT_NUMBER"
echo ""
echo "📝 Prochaines étapes :"
echo "1. Mettre à jour le numéro de project dans .github/workflows/add-to-project.yml"
echo "   PROJECT_NUMBER=$PROJECT_NUMBER"
echo ""
echo "2. Configurer les champs personnalisés dans l'interface web"
echo "   $PROJECT_URL/settings"
echo ""
echo "3. Créer des vues personnalisées (Kanban, Table, Roadmap)"
echo ""
echo "4. Ajouter des issues existantes au project :"
echo "   gh project item-add $PROJECT_NUMBER --owner $ORG --url <ISSUE_URL>"
echo ""
echo "📚 Guide complet : docs/GITHUB_PROJECT_GUIDE.md"
echo "================================================"

# Sauvegarder les informations du project
cat > .github/project-info.json <<EOF
{
  "project_number": $PROJECT_NUMBER,
  "project_url": "$PROJECT_URL",
  "organization": "$ORG",
  "repositories": [
    "$REPO1",
    "$REPO2"
  ],
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo ""
echo "💾 Informations sauvegardées dans .github/project-info.json"
