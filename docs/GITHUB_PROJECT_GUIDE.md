# GitHub Project Guide - FinOps Tag Compliance Suite

## Vue d'ensemble

Ce guide explique comment utiliser le GitHub Project pour coordonner le développement entre :
- **MCP Server** (`finops-tag-compliance-mcp`) - Serveur MCP pour validation de tags AWS
- **Policy Generator** (`tagging-policy-generator`) - Interface web pour créer des politiques de tagging

## Structure du Project

### 🏗️ Architecture

```
FinOps Tag Compliance Suite
│
├── 🔧 MCP Server Repository
│   ├── API backend (FastAPI)
│   ├── 8 outils MCP
│   ├── Services de conformité
│   └── Intégration AWS
│
└── 🌐 Policy Generator Repository
    ├── Interface web
    ├── Éditeur de politiques
    ├── Validation en temps réel
    └── Export de politiques JSON
```

### 📊 Vues du Project

#### 1. **Board View (Kanban)**
- **Backlog** : Issues non planifiées
- **Todo** : Prêt pour développement
- **In Progress** : En cours de développement
- **Review** : En revue de code
- **Done** : Complété

#### 2. **Table View**
Colonnes :
- Status
- Title
- Component (MCP Server / Policy Generator / Both)
- Priority
- Assignee
- Labels
- Repository

#### 3. **Roadmap View**
- Timeline visuelle des features
- Dates de release
- Dépendances entre repos

## 🏷️ Champs personnalisés

### Component
Indique quel projet est concerné :
- `MCP Server` - Issues spécifiques au serveur MCP
- `Policy Generator` - Issues spécifiques à l'interface web
- `Integration` - Features qui touchent les deux projets
- `Infrastructure` - DevOps, CI/CD, déploiement
- `Documentation` - Docs, guides, exemples

### Priority
- `🔴 High` - Bloquant, bug critique, security
- `🟡 Medium` - Feature importante, amélioration
- `🟢 Low` - Nice-to-have, optimisation

### Release
- `v1.0` - MVP Phase 1 (AWS uniquement)
- `v1.1` - Améliorations post-MVP
- `v2.0` - Support multi-cloud (Azure, GCP)
- `Backlog` - Non planifié

### Cost Impact
Impact sur les coûts AWS/Azure :
- `High` - Peut réduire les coûts de >10%
- `Medium` - Impact modéré (5-10%)
- `Low` - Impact mineur (<5%)
- `None` - Pas d'impact direct

## 🔗 Workflow inter-repos

### Lien entre les projets

Le Policy Generator produit des fichiers `tagging_policy.json` qui sont consommés par le MCP Server.

**Flux de travail typique** :
1. User crée une politique dans Policy Generator
2. Exporte le JSON
3. Place le fichier dans `policies/tagging_policy.json` du MCP Server
4. Le MCP Server valide et applique la politique

### Issues liées entre repos

Utilisez les références croisées dans les issues :

```markdown
# Dans MCP Server issue
Related to OptimNow/tagging-policy-generator#42

# Dans Policy Generator issue
Blocks OptimNow/finops-tag-compliance-mcp#15
```

## 📋 Templates d'issues recommandés

### Feature Request
```markdown
## Description
[Description de la feature]

## Component
- [ ] MCP Server
- [ ] Policy Generator
- [ ] Both

## Use Case
[Cas d'usage métier]

## Technical Details
[Détails techniques]

## Dependencies
- Depends on: #XX
- Blocks: #YY
```

### Bug Report
```markdown
## Bug Description
[Description du bug]

## Affected Component
- [ ] MCP Server
- [ ] Policy Generator
- [ ] Integration

## Steps to Reproduce
1. ...
2. ...

## Expected vs Actual
**Expected**: ...
**Actual**: ...

## Environment
- Version:
- AWS Region:
- Python version:
```

## 🤖 Automatisation

### Auto-add issues to Project
Le workflow `.github/workflows/add-to-project.yml` ajoute automatiquement :
- Toutes les nouvelles issues
- Toutes les nouvelles PRs
- Auto-set le champ "Component" selon le repo

### Labels recommandés

**Par type** :
- `bug` 🐛 - Bugs à corriger
- `enhancement` ✨ - Nouvelles features
- `documentation` 📚 - Docs
- `security` 🔒 - Security issues

**Par composant** :
- `mcp-server` - Code MCP Server
- `policy-generator` - Code Policy Generator
- `integration` - Entre les deux projets

**Par priorité** :
- `priority:high` - Urgent
- `priority:medium` - Normal
- `priority:low` - Quand possible

**Par statut** :
- `good first issue` - Pour nouveaux contributeurs
- `help wanted` - Besoin d'aide
- `blocked` - Bloqué par autre chose

## 📅 Milestones recommandés

Créez des milestones synchronisés entre les deux repos :

### v1.0 - MVP (Phase 1)
**Date cible** : [DATE]
**Scope** :
- MCP Server avec 8 outils AWS
- Policy Generator avec éditeur de base
- Documentation complète
- Tests unitaires + intégration

### v1.1 - Post-MVP Improvements
**Date cible** : [DATE]
**Scope** :
- Amélioration UI Policy Generator
- Nouveaux services AWS
- Optimisation performance
- Feedback utilisateurs

### v2.0 - Multi-Cloud
**Date cible** : [DATE]
**Scope** :
- Support Azure
- Support GCP
- Policy Generator multi-cloud
- Comparaison cross-cloud

## 🔍 Recherche et filtres utiles

### Issues MCP Server en cours
```
is:issue is:open repo:OptimNow/finops-tag-compliance-mcp
```

### PRs Policy Generator en review
```
is:pr is:open repo:OptimNow/tagging-policy-generator review:required
```

### Issues bloquantes haute priorité
```
is:issue is:open label:blocked label:priority:high
```

### Features cross-repo
```
is:issue is:open label:integration
```

## 🎯 Best Practices

1. **Toujours tagger le Component** dans les issues
2. **Lier les issues liées** entre repos avec références
3. **Utiliser les milestones** pour tracking des releases
4. **Mettre à jour le status** régulièrement
5. **Fermer les issues** avec message de résolution
6. **Documenter les décisions** dans les issues/PRs

## 📞 Ressources

- **MCP Server README** : [Lien]
- **Policy Generator README** : [Lien]
- **API Documentation** : [Lien]
- **Slack/Discord** : [Lien si applicable]

## 🚀 Quick Start

### Créer le Project
```bash
# Via GitHub CLI
gh project create --owner OptimNow --title "FinOps Tag Compliance Suite"

# Lier les repos
gh project link <NUMBER> --owner OptimNow --repo finops-tag-compliance-mcp
gh project link <NUMBER> --owner OptimNow --repo tagging-policy-generator
```

### Ajouter une issue au Project
```bash
# Créer issue et l'ajouter
gh issue create --repo OptimNow/finops-tag-compliance-mcp \
  --title "Add support for ECS tasks" \
  --body "Description..." \
  --project "FinOps Tag Compliance Suite"
```

### Déplacer une issue dans le board
```bash
gh project item-edit --id <ITEM_ID> --project-id <PROJECT_ID> \
  --field-id <STATUS_FIELD_ID> --value "In Progress"
```

---

**Maintenu par** : OptimNow Team
**Dernière mise à jour** : 2026-01-14
