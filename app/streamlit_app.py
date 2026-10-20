"""Local demo UI.

    uv run --group ui streamlit run app/streamlit_app.py

Needs GEMINI_API_KEY (and DATABASE_URL to use pgvector instead of the
in-memory index). Run from the repository root.
"""

import streamlit as st

from morocco_tax_agent.agent.graph import ask, default_graph
from morocco_tax_agent.tools.salary import MissingRatesError, compute_net_salary

st.set_page_config(page_title="Assistant fiscal marocain", page_icon="🧾")
st.title("Assistant fiscal marocain")
st.caption("Impôt sur le revenu des salariés (CGI 2026) · CNSS/AMO · salaire net. "
           "Information générale, pas un conseil fiscal ou juridique.")


@st.cache_resource
def graph():
    return default_graph()


with st.sidebar:
    st.header("Calculateur brut → net")
    gross = st.number_input("Salaire brut mensuel (DH)", min_value=0.0, value=10000.0, step=500.0)
    dependents = st.number_input("Personnes à charge", min_value=0, max_value=10, value=0)
    with st.expander("Indemnités exonérées (bulletin)"):
        contributable = st.number_input("Brut cotisable CNSS (DH, 0 = brut)", min_value=0.0, value=0.0)
        taxable = st.number_input("Brut imposable (DH, 0 = brut)", min_value=0.0, value=0.0)
    if st.button("Calculer") and gross > 0:
        try:
            r = compute_net_salary(
                gross, int(dependents),
                contributable_gross=contributable or None, taxable_gross=taxable or None,
            )
        except (MissingRatesError, ValueError) as error:
            st.error(str(error))
        else:
            st.metric("Net mensuel", f"{r.net_monthly:,.2f} DH")
            st.json(r.model_dump(mode="json"))

if "history" not in st.session_state:
    st.session_state.history = []

for role, text in st.session_state.history:
    st.chat_message(role).markdown(text)

if question := st.chat_input("Ex. : Quel est le barème de l'impôt sur le revenu en 2026 ?"):
    st.chat_message("user").markdown(question)
    with st.spinner("Recherche dans le CGI…"):
        answer = ask(graph(), question)
    st.chat_message("assistant").markdown(answer)
    st.session_state.history += [("user", question), ("assistant", answer)]
