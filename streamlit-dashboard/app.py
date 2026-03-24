"""
🦐 Smart Shrimp Farm — Dashboard de Monitoramento
===================================================
Dashboard Streamlit para monitoramento em tempo real de viveiros de camarão.
Exibe dados de sensores, alertas, eventos de manejo e estudos de produção.
"""

import streamlit as st
from datetime import datetime
import os

from data_loader import load_dashboard_data

# ============================================================================
# Configuração da página
# ============================================================================
st.set_page_config(
    page_title="Smart Shrimp Farm",
    page_icon="🦐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# CSS customizado
# ============================================================================
st.markdown("""
<style>
    /* Header */
    .main-header {
        background: linear-gradient(135deg, #01696F 0%, #0C4E54 100%);
        color: white;
        padding: 1.2rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.6rem;
        font-weight: 700;
    }
    .main-header p {
        margin: 0.3rem 0 0 0;
        opacity: 0.85;
        font-size: 0.9rem;
    }
    
    /* Metric cards */
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        border-left: 4px solid #01696F;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .metric-card.warning { border-left-color: #f1c40f; }
    .metric-card.critical { border-left-color: #e74c3c; }
    .metric-card .label { font-size: 0.78rem; color: #7A7974; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-card .value { font-size: 1.8rem; font-weight: 700; color: #28251D; line-height: 1.2; }
    .metric-card .unit { font-size: 0.85rem; color: #7A7974; font-weight: 400; }
    .metric-card .status { font-size: 0.8rem; margin-top: 0.2rem; }
    
    /* Status badges */
    .badge-green { background: #d4edda; color: #155724; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-yellow { background: #fff3cd; color: #856404; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    .badge-red { background: #f8d7da; color: #721c24; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: #1C1B19;
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #CDCCCA;
    }
    
    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Alert cards */
    .alert-critical {
        background: #fff5f5;
        border-left: 4px solid #e74c3c;
        padding: 0.8rem 1rem;
        border-radius: 6px;
        margin-bottom: 0.5rem;
    }
    .alert-warning {
        background: #fffbeb;
        border-left: 4px solid #f1c40f;
        padding: 0.8rem 1rem;
        border-radius: 6px;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Cache de dados (API real ou simulacao)
# ============================================================================
@st.cache_data(ttl=60)
def load_data(source_mode: str, api_base_url: str):
    """Carrega dados do backend real (ou simulados em fallback)."""
    return load_dashboard_data(source_mode=source_mode, api_base_url=api_base_url)


# ============================================================================
# Sidebar / Navegação
# ============================================================================
api_base_url = os.getenv("BACKEND_API_URL", "http://localhost:8000").rstrip("/")

source_options = {
    "Auto (tenta API)": "auto",
    "API real": "api",
    "Simulacao": "sim",
}

default_source = os.getenv("DASHBOARD_DATA_SOURCE", "auto").lower()
default_label = "Auto (tenta API)"
for label, value in source_options.items():
    if value == default_source:
        default_label = label
        break

selected_source_label = st.sidebar.selectbox(
    "Fonte de dados",
    list(source_options.keys()),
    index=list(source_options.keys()).index(default_label),
)

selected_source_mode = source_options[selected_source_label]
data, data_info = load_data(selected_source_mode, api_base_url)

st.sidebar.markdown("## 🦐 Smart Shrimp Farm")
st.sidebar.markdown("---")

if data_info["source"] == "api":
    st.sidebar.success(f"API conectada: {api_base_url}")
else:
    st.sidebar.warning("Modo simulacao ativo")
    if data_info.get("error"):
        st.sidebar.caption(f"Fallback: {data_info['error']}")

st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navegação",
    ["📊 Visão Geral", "🔍 Detalhes do Viveiro", "📈 Estudos de Produção", "🚨 Alertas e Eventos"],
    label_visibility="collapsed"
)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Atualizado:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")
st.sidebar.markdown(f"**Viveiros ativos:** {len(data['ponds'][data['ponds']['status'] == 'active'])}")

n_critical = len(data['alerts'][data['alerts']['severity'] == 'critical']) if not data['alerts'].empty else 0
n_warning = len(data['alerts'][data['alerts']['severity'] == 'warning']) if not data['alerts'].empty else 0
if n_critical > 0:
    st.sidebar.error(f"🔴 {n_critical} alerta(s) crítico(s)")
if n_warning > 0:
    st.sidebar.warning(f"🟡 {n_warning} alerta(s) de atenção")

if st.sidebar.button("🔄 Atualizar Dados"):
    st.cache_data.clear()
    st.rerun()


# ============================================================================
# Roteamento de páginas
# ============================================================================
if page == "📊 Visão Geral":
    from pages.visao_geral import render
    render(data)
elif page == "🔍 Detalhes do Viveiro":
    from pages.detalhes_viveiro import render
    render(data)
elif page == "📈 Estudos de Produção":
    from pages.estudos_producao import render
    render(data)
elif page == "🚨 Alertas e Eventos":
    from pages.alertas_eventos import render
    render(data)
