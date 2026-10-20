# morocco-tax-agent

Assistant fiscal et social marocain : RAG + agent qui répond aux questions d'un salarié en citant l'article exact du Code général des impôts (CGI), et qui calcule le salaire net à partir du brut avec des outils Python testés.

Projet personnel de Youssef (Master IA, FSBM). But : une démo en ligne pour candidater chez **Cnexia** (LLM, RAG, agents, Gemini, GCP) et décrocher un PFE en IA générative.

Fiche projet (plan détaillé, sources, évaluation) : https://claude.ai/code/artifact/121b24ed-b32b-46d4-8a6a-ebdcb35ff67c

## Périmètre de la v1 (en ligne le 2 novembre 2026)

- **Inclus** : impôt sur le revenu des salariés (CGI 2026, Livre I, Titre II, articles 21 à 86 ; barème à l'article 73) ; cotisations CNSS/AMO ; calcul du salaire brut vers net.
- **Exclus (v2, après le 10 novembre)** : Code du travail, statut d'auto-entrepreneur.
- **Hors périmètre** (TVA, IS, droits d'enregistrement, cas personnel complexe) : l'agent refuse poliment et renvoie vers la source officielle.
- Chaque réponse se termine par : « Information générale, pas un conseil fiscal ou juridique. »

## Stack

Python 3.12, `uv` · Gemini (API Gemini, puis Vertex AI) · LangGraph · PostgreSQL + pgvector (Supabase ou Neon) · FastAPI · Streamlit · Docker · GCP Cloud Run · pytest · Pydantic.

## Commandes

```bash
uv sync
uv run pytest -q
uv run python scripts/check_sources.py data/raw/*.pdf      # contrôle qualité des PDF + manifest.json
uv run python -m morocco_tax_agent.sources.cgi data/raw/cgi_2026_fr.pdf --edition 2026
```

## Sources officielles (et seulement elles)

Base légale : la loi 2-00, article 8, exclut du droit d'auteur les textes officiels législatifs, administratifs et judiciaires. On n'utilise **jamais** les compilations de cabinets ou de sites tiers. Elles se contredisent d'ailleurs sur les taux CNSS.

| Fichier (`data/raw/`, ignoré par Git) | Source | État |
| --- | --- | --- |
| `cgi_2026_fr.pdf` | https://www.tax.gov.ma/wps/wcm/connect/08712531-1e81-4e28-a38b-2bd9edf8e09e/CGI+2026+FR.pdf?MOD=AJPERES. `curl` reçoit une page HTML anti-robot : il faut télécharger depuis un navigateur. | 775 pages, texte extractible, SHA-256 `28f85c69…3b03022`. Titre IR : pages PDF 57 à 142. |
| Taux CNSS/AMO salarié (`data/processed/cnss_rates_sources.json`, versionné) | Tableau « Paiement de vos cotisations sociales » de cnss.ma, [capture Wayback du 25/03/2025](https://web.archive.org/web/20250325185811/https://cnss.ma/fr/content/paiement-de-vos-cotisations-sociales) (retiré du site actuel), et FAQ cnss.ma (AMO 2,26 % sans plafond ; plafond 6 000 DH depuis avril 2002) | Validé par Youssef le 20 oct : 0,52 % (dont IPE 0,19 %) + 3,96 % sur 6 000 DH max, AMO 2,26 % sans plafond. `cnss_cotisations_2026.webp` n'est qu'une illustration sans chiffres. |
| Arrêté n° 1314.25 du 19 mai 2025 (assiette CNSS) | BO n° 7443 (édition arabe, 29/09/2025), scan PDF sur https://www.cnss.ma/fr/reglementation. `curl` reçoit une page anti-robot. | Lu en entier : 44 indemnités exclues de l'assiette, avec plafonds (transport 500/750 DH, panier 2 × SMIG horaire/jour, représentation 10 % du salaire de base…). Ne change ni les taux ni le plafond. Le calculateur prend le brut cotisable et le brut imposable du bulletin au lieu de coder ces règles. Le PDF français « assiette de cotisation » de la même page est l'ancienne note circulaire de 2005. |
| `code_travail_fr_2011.pdf` (v2) | adala.justice.gov.ma | Consolidé en 2011, issu d'un OCR ; articles 256, 327 et 334 non détectés ; ne contient pas la loi 02-21 (2021). |

## Décisions déjà prises (et pourquoi)

Youssef doit pouvoir les défendre en entretien. Garde-les, ou propose explicitement d'en changer.

- **Un chunk = un article.** On récupère l'unité qu'on cite. Les articles longs (57 et 73 dépassent 8 000 caractères) sont redécoupés à l'indexation par paragraphe (`I.-`, `II.-`), jamais au milieu d'un paragraphe.
- **Le corps du texte et les notes sont séparés par la taille de police** (corps ≥ 9 pt, notes et appels de note < 9 pt). Les appels de note sont collés aux mots : « Article 47290.- » = article 47 + note 290.
- **Les notes de bas de page sont gardées** dans `amendments` : elles indiquent quelle loi de finances a modifié l'article.
- **Les bornes du titre sont trouvées par ses en-têtes**, pas par des numéros de page, et la numérotation est contrôlée. L'édition 2027 doit se découper sans changer le code.
- **Le LLM ne calcule jamais.** Les chiffres viennent d'outils Python déterministes et testés (`compute_net_salary`).
- **Les barèmes sont versionnés par année** (`rates/2026.yaml`) et **extraits des sources officielles**, jamais écrits de mémoire. Chaque valeur est comparée au texte officiel dans un test.
- **Le corpus est versionné par édition.** On démontre la réindexation en comparant les barèmes 2025 et 2026.

## Règles

- Ne jamais commiter de PDF, de `.env`, de clé d'API ni de donnée personnelle. Les bulletins de paie de test ne gardent que le mois, le brut, le brut cotisable CNSS, le brut imposable, la situation familiale et le net : ni nom, ni CIN, ni numéro CNSS.
- **La vérité terrain vient de Youssef, pas de l'IA** : l'article attendu de chaque question d'évaluation et le net des bulletins réels. Tu peux proposer des formulations de questions, jamais les réponses attendues.
- Les tests passent avant chaque commit. Messages de commit au format conventionnel (`feat:`, `fix:`, `chore:`…).
- Code, commentaires et README en anglais. Échanges avec Youssef en français. L'agent répond en français.
- Youssef est sous **Windows + Git Bash** : donne des commandes bash, et garde les fins de ligne LF (`.gitattributes` est en place).
- Demande avant toute action qui coûte de l'argent ou qui est difficile à annuler (déploiement GCP, création de ressources cloud, `git push --force`).

## Façon de travailler avec Youssef

- C'est toi qui écris le code. Après chaque fichier important, explique **en 3 ou 4 phrases les choix qu'il devra défendre en entretien** (pourquoi ce découpage, pourquoi cet outil, comment on sait que c'est juste).
- Recommande la meilleure option avec ta raison, plutôt que de lui faire choisir entre plusieurs options.
- Avance étape par étape et fais valider avant de passer à la suivante.
- Il travaille environ 2 h par jour. Garde les étapes courtes.

## Plan

| Dates | Étape | Livrable | État |
| --- | --- | --- | --- |
| 20–21 oct | Sources téléchargées et contrôlées, dépôt renommé, découpage du titre IR par article | `manifest.json`, `cgi_2026_ir_articles.jsonl` (74 articles, 21 → 86) | Fait |
| 22–23 oct | Barème de l'article 73 et taux CNSS/AMO en Pydantic, comparés aux sources officielles | `rates/2026.yaml` + tests | Fait : IR (art. 59, 73, 74) et CNSS/AMO, chaque valeur testée contre le texte officiel |
| 24–26 oct | Calculateur brut vers net | `compute_net_salary`, 30 cas réels à 1 DH près | Code et tests faits (taux officiels, brut cotisable et brut imposable optionnels) ; manquent les 30 bulletins réels |
| 27–29 oct | Indexation pgvector, agent LangGraph (`search_tax_code`, `compute_net_salary`), avertissement, refus hors périmètre | Streamlit en local, 30 premiers cas d'évaluation | Code et tests hors ligne faits ; jamais lancé contre Gemini ni Postgres ; 30 questions proposées, vérité terrain à remplir |
| 30 oct | Marge | — | — |
| 31 oct – 2 nov | FastAPI, Docker, Cloud Run, README | **v1 en ligne** | FastAPI, Dockerfile, README faits ; image jamais construite ; Cloud Run à faire |
| 3–9 nov | 100 cas d'évaluation + RAGAS, barèmes 2025 vs 2026, CI GitHub Actions, vidéo de 2 min | Chiffres dans le README, **candidature Cnexia (limite 10 nov)** | À faire |

Si on déborde : on consomme la marge, puis on réduit l'évaluation de la v1 à 30 cas. Le calculateur testé et la citation d'article ne se négocient pas.

## Évaluation (`eval/cases.jsonl`, 100 cas)

| Bloc | Cas | Vérité attendue | Mesure |
| --- | --- | --- | --- |
| IR des salariés | 40 | Numéro d'article du CGI 2026 | Article attendu dans les 5 premiers passages ; fidélité RAGAS |
| CNSS / AMO | 15 | Passage de la source cnss.ma | Bonne source ; chiffre exact |
| Calcul brut vers net | 30 | Net du bulletin réel | Outil appelé ; écart ≤ 1 DH |
| Hors périmètre | 15 | Refus + renvoi vers la source officielle | Taux de refus correct |
