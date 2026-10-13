#!/bin/bash
cd ~/Documents/PROJET/dataflow360

BRANCHES=(
  "develop"
  "feature/backend"
  "feature/ci-github-actions"
  "feature/dashboard-assane"
  "feature/data-engineering"
  "feature/docker-compose"
  "feature/fraud-detection"
  "main"
)

for branch in "${BRANCHES[@]}"; do
  echo ""
  echo "=== $branch ==="
  if git show-ref --verify --quiet "refs/heads/$branch"; then
    git checkout "$branch"
  else
    git checkout -b "$branch" "origin/$branch"
  fi
  git pull origin "$branch"
  git push origin "$branch"
done

git checkout feature/backend
echo ""
echo "🎉 Terminé"

