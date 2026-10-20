---
title: Morocco Tax Agent
emoji: 🧾
colorFrom: green
colorTo: red
sdk: docker
app_port: 8080
pinned: false
short_description: Moroccan payroll tax assistant citing the CGI 2026
---

# morocco-tax-agent (demo)

Assistant for Moroccan employees' tax questions: answers from the official General
Tax Code (CGI 2026) citing the exact article, and computes net salary with tested tools.

- `POST /ask` — question in French; answer citing the CGI article (rate-limited: free Gemini quota).
- `POST /net-salary` — gross to net calculator, no LLM.
- Interactive docs: `/docs`.

Source code, sources and evaluation: https://github.com/Youssef-srf/morocco-tax-agent

*Information générale, pas un conseil fiscal ou juridique.*
