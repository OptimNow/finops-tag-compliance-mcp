# Configuration GitHub Project - Guide Rapide (Français)

## Vue d'ensemble

Ce guide vous explique comment créer un **GitHub Project** unique qui gère à la fois :
- ✅ **MCP Server** (ce repository)
- ✅ **Tagging Policy Generator** (repository séparé)

Les deux projets sont liés car le Policy Generator crée les fichiers JSON que le MCP Server utilise.

## 🚀 Méthode rapide : Script automatique

### Prérequis
```bash
# Installer GitHub CLI si nécessaire
# macOS
brew install gh

# Linux
sudo apt install gh

# Windows
winget install GitHub.cli

# S'authentifier
gh auth login
```

### Lancer le script
```bash
# Depuis la racine du projet MCP
./scripts/setup-github-project.sh
```

Le script va :
1. ✅ Créer le GitHub Project "FinOps Tag Compliance Suite"
2. ✅ Lier les deux repositories au Project
3. ✅ Créer les labels recommandés
4. ✅ Créer le milestone v1.0
5. ✅ Sauvegarder les infos dans `.github/project-info.json`

### Après le script

1. **Mettre à jour le workflow**
   ```bash
   # Récupérer le numéro de project
   PROJECT_NUMBER=$(jq -r '.project_number' .github/project-info.json)
   echo "Numéro de project : $PROJECT_NUMBER"

   # Éditer .github/workflows/add-to-project.yml
   # Remplacer <PROJECT_NUMBER> par le numéro réel
   ```

2. **Configurer les champs personnalisés** (via interface web)
   - Allez sur le Project
   - Settings → Custom fields
   - Ajoutez : Component, Priority, Release, Cost Impact

3. **Créer les vues**
   - Board (Kanban)
   - Table (Liste détaillée)
   - Roadmap (Timeline)

## 📋 Méthode manuelle : Interface web

### Étape 1 : Créer le Project
1. Allez sur `https://github.com/orgs/OptimNow/projects`
2. Cliquez **"New project"**
3. Choisissez le template **"Team backlog"**
4. Nommez-le : `FinOps Tag Compliance Suite`
5. Cliquez **"Create project"**

### Étape 2 : Lier les repositories
1. Dans le Project, cliquez **"..."** (menu)
2. **Settings** → **Linked repositories**
3. Ajoutez :
   - `OptimNow/finops-tag-compliance-mcp`
   - `OptimNow/tagging-policy-generator`

### Étape 3 : Créer les champs personnalisés
Dans Settings → **Custom fields**, créez :

#### 📦 Component (Single select)
- MCP Server
- Policy Generator
- Integration
- Infrastructure
- Documentation

#### 🎯 Priority (Single select)
- High (🔴)
- Medium (🟡)
- Low (🟢)

#### 📅 Release (Single select)
- v1.0
- v1.1
- v2.0
- Backlog

#### 💰 Cost Impact (Single select)
- High
- Medium
- Low
- None

### Étape 4 : Créer les vues

#### Vue 1 : Board (Kanban)
1. Cliquez **"+ New view"** → **Board**
2. Nommez : "Kanban Board"
3. Colonnes :
   - 📥 Backlog
   - 📝 Todo
   - 🏃 In Progress
   - 👀 Review
   - ✅ Done

#### Vue 2 : Table (Liste)
1. **"+ New view"** → **Table**
2. Nommez : "All Items"
3. Colonnes visibles :
   - Status
   - Title
   - Component
   - Priority
   - Assignees
   - Repository
   - Labels

#### Vue 3 : Roadmap (Timeline)
1. **"+ New view"** → **Roadmap**
2. Nommez : "Release Timeline"
3. Grouper par : Release
4. Configurer les dates de milestone

## 🔗 Lier des issues existantes au Project

### Via GitHub CLI
```bash
# Lister les issues du MCP Server
gh issue list --repo OptimNow/finops-tag-compliance-mcp

# Ajouter une issue au Project
gh project item-add <PROJECT_NUMBER> \
  --owner OptimNow \
  --url https://github.com/OptimNow/finops-tag-compliance-mcp/issues/5

# Faire pareil pour Policy Generator
gh project item-add <PROJECT_NUMBER> \
  --owner OptimNow \
  --url https://github.com/OptimNow/tagging-policy-generator/issues/10
```

### Via interface web
1. Ouvrez une issue
2. Sur la droite, section **"Projects"**
3. Sélectionnez votre Project
4. L'issue est ajoutée automatiquement

## 🤖 Automatisation

### Workflow GitHub Actions (déjà configuré)
Le fichier `.github/workflows/add-to-project.yml` ajoute automatiquement :
- Toutes les nouvelles issues
- Toutes les nouvelles PRs
- Auto-définit le champ "Component" selon le repo

⚠️ **Important** : Remplacez `<PROJECT_NUMBER>` par le vrai numéro après création.

### Labels automatiques
Créez des labels standards dans les deux repos :

**Labels de composant** :
- `mcp-server` (bleu) - Issues du MCP Server
- `policy-generator` (violet) - Issues du Policy Generator
- `integration` (violet foncé) - Issues cross-repo

**Labels de priorité** :
- `priority:high` (rouge)
- `priority:medium` (jaune)
- `priority:low` (vert)

## 📊 Utilisation quotidienne

### Créer une nouvelle issue et l'ajouter au Project
```bash
# Pour MCP Server
gh issue create \
  --repo OptimNow/finops-tag-compliance-mcp \
  --title "Add support for ECS tasks" \
  --body "We need to scan ECS tasks for tag compliance" \
  --label "enhancement,mcp-server,priority:medium" \
  --project "FinOps Tag Compliance Suite"

# Pour Policy Generator
gh issue create \
  --repo OptimNow/tagging-policy-generator \
  --title "Add dark mode toggle" \
  --body "Users want dark mode for late-night policy editing" \
  --label "enhancement,policy-generator,priority:low" \
  --project "FinOps Tag Compliance Suite"
```

### Déplacer une carte dans le board
```bash
# Via CLI (nécessite l'ID de l'item)
gh project item-edit \
  --id <ITEM_ID> \
  --project-id <PROJECT_ID> \
  --field-id <STATUS_FIELD_ID> \
  --value "In Progress"

# Ou via drag & drop dans l'interface web (plus simple !)
```

### Lier des issues entre repos
Dans le corps d'une issue, utilisez :

```markdown
# Dans une issue MCP Server
Cette feature nécessite d'abord OptimNow/tagging-policy-generator#42

# Dans une issue Policy Generator
Ceci va débloquer OptimNow/finops-tag-compliance-mcp#15
```

GitHub créera automatiquement les liens bidirectionnels.

## 🎯 Workflows recommandés

### Workflow 1 : Nouvelle feature cross-repo
1. Créer une issue dans le **Policy Generator** pour l'UI
2. Créer une issue dans le **MCP Server** pour l'intégration
3. Lier les deux issues avec références croisées
4. Ajouter label `integration` aux deux
5. Travailler dessus en parallèle ou séquentiellement

### Workflow 2 : Bug fix
1. Issue créée automatiquement ajoutée au Project
2. Auto-classée dans "Backlog"
3. Triée par priorité
4. Déplacée en "Todo" lors du sprint planning
5. Assignée à un dev → "In Progress"
6. PR créée → "Review"
7. PR merged → "Done"

### Workflow 3 : Release planning
1. Créer un milestone `v1.1` dans les deux repos
2. Dans la vue Roadmap, grouper par Release
3. Assigner des issues au milestone
4. Suivre la progression visuellement
5. Fermer le milestone quand tout est mergé

## 📈 Métriques et rapports

### Voir la vélocité
```bash
# Issues fermées ce mois dans les deux repos
gh issue list \
  --repo OptimNow/finops-tag-compliance-mcp \
  --state closed \
  --search "closed:>2026-01-01" \
  --limit 100

gh issue list \
  --repo OptimNow/tagging-policy-generator \
  --state closed \
  --search "closed:>2026-01-01" \
  --limit 100
```

### Export du Project
Via l'interface web :
1. Ouvrez le Project
2. Vue Table
3. Menu **"..."** → **Export**
4. Téléchargez en CSV

## 🔍 Recherches utiles

### Issues haute priorité non assignées
```
is:issue is:open label:priority:high no:assignee
```

### PRs en attente de review
```
is:pr is:open review:required
```

### Issues d'intégration cross-repo
```
is:issue is:open label:integration
```

### Bugs MCP Server
```
is:issue is:open label:bug repo:OptimNow/finops-tag-compliance-mcp
```

## 🆘 Dépannage

### Le Project n'apparaît pas dans la liste
- Vérifiez que vous avez les permissions sur l'organisation
- Le Project doit être au niveau org, pas user

### Les issues ne sont pas ajoutées automatiquement
- Vérifiez que le workflow `.github/workflows/add-to-project.yml` est activé
- Vérifiez le numéro de Project dans le workflow
- Le token GitHub doit avoir les permissions `project`

### Je ne vois pas les champs personnalisés
- Ils doivent être créés manuellement via Settings
- L'API GraphQL peut aussi les créer, mais c'est complexe

### Les deux repos ne se parlent pas
- Utilisez des références croisées : `OptimNow/repo#123`
- Ajoutez le label `integration` pour visibilité
- Documentez les dépendances dans les issues

## 📚 Ressources

- **Documentation GitHub Projects** : https://docs.github.com/en/issues/planning-and-tracking-with-projects
- **GitHub CLI** : https://cli.github.com/manual/
- **Guide complet** : `docs/GITHUB_PROJECT_GUIDE.md`
- **Script setup** : `scripts/setup-github-project.sh`

## ✅ Checklist de setup

- [ ] Installer GitHub CLI (`gh`)
- [ ] S'authentifier (`gh auth login`)
- [ ] Lancer `./scripts/setup-github-project.sh`
- [ ] Créer les champs personnalisés dans l'UI
- [ ] Créer les 3 vues (Board, Table, Roadmap)
- [ ] Mettre à jour le workflow avec le bon PROJECT_NUMBER
- [ ] Ajouter les issues existantes au Project
- [ ] Créer le milestone v1.0 dans les deux repos
- [ ] Lier les issues connexes entre repos
- [ ] Tester en créant une nouvelle issue

---

**Créé le** : 2026-01-14
**Auteur** : OptimNow Team
**Version** : 1.0
