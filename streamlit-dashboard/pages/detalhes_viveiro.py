"""
Página: Detalhes do Viveiro
Gráficos de séries temporais, timeline de eventos e recomendações.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from data_simulator import PARAM_CONFIG, get_status_emoji, get_status_color


def render(data: dict):
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Detalhes do Viveiro</h1>
        <p>Análise detalhada de parâmetros de qualidade da água</p>
    </div>
    """, unsafe_allow_html=True)
    
    ponds = data['ponds']
    sensor_data = data['sensor_data']
    events = data['events']
    
    active_ponds = ponds[ponds['status'] == 'active']
    
    # --- Seletor de viveiro e período ---
    col1, col2 = st.columns([2, 1])
    with col1:
        pond_options = {row['id']: f"{row['name']} ({row['system_type'].title()} · {row['area_m2']:,.0f} m²)" 
                       for _, row in active_ponds.iterrows()}
        selected_pond = st.selectbox("Selecione o Viveiro", options=list(pond_options.keys()),
                                      format_func=lambda x: pond_options[x])
    with col2:
        period = st.selectbox("Período", ["Últimas 24h", "Últimos 3 dias", "Últimos 7 dias"])
    
    hours_map = {"Últimas 24h": 24, "Últimos 3 dias": 72, "Últimos 7 dias": 168}
    hours = hours_map[period]
    
    if selected_pond not in sensor_data:
        st.warning("Sem dados para este viveiro.")
        return
    
    df = sensor_data[selected_pond]
    cutoff = datetime.now() - timedelta(hours=hours)
    df_period = df[df['timestamp'] >= cutoff].copy()
    
    if df_period.empty:
        st.warning("Sem dados no período selecionado.")
        return
    
    # --- Cards de valores atuais ---
    st.subheader("Valores Atuais")
    latest = df_period.iloc[-1]
    
    params = ['temperature', 'ph', 'dissolved_oxygen', 'salinity', 'turbidity', 'tds']
    cols = st.columns(6)
    
    for i, param in enumerate(params):
        cfg = PARAM_CONFIG[param]
        val = latest.get(param)
        if val is not None and pd.notna(val):
            color = get_status_color(val, param)
            emoji = get_status_emoji(val, param)
            
            # Calcular delta (variação nas últimas 6h)
            six_h_ago = df_period[df_period['timestamp'] >= datetime.now() - timedelta(hours=6)]
            delta = None
            if not six_h_ago.empty and len(six_h_ago) > 1:
                delta = val - six_h_ago.iloc[0][param]
            
            with cols[i]:
                delta_str = f"{delta:+{cfg['format']}}" if delta is not None else "--"
                st.metric(
                    label=f"{cfg['icon']} {cfg['label']}",
                    value=f"{val:{cfg['format']}} {cfg['unit']}",
                    delta=f"{delta_str} (6h)",
                )
                st.markdown(f"{emoji} {'Ideal' if color == 'green' else 'Atenção' if color == 'orange' else 'Crítico'}")
    
    st.markdown("---")
    
    # --- Gráficos de séries temporais ---
    st.subheader("Séries Temporais")
    
    # Tabs para agrupar parâmetros
    tab1, tab2, tab3 = st.tabs(["🌡️ Temp / OD / pH", "🧂 Salinidade / TDS", "🌊 Turbidez / EC"])
    
    with tab1:
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=("Temperatura (°C)", "Oxigênio Dissolvido (mg/L)", "pH")
        )
        
        # Temperatura
        fig.add_trace(go.Scatter(
            x=df_period['timestamp'], y=df_period['temperature'],
            mode='lines', name='Temperatura',
            line=dict(color='#e74c3c', width=1.5),
            hovertemplate='%{x|%d/%m %H:%M}<br>%{y:.1f}°C<extra></extra>',
        ), row=1, col=1)
        # Faixas ideais
        fig.add_hrect(y0=26, y1=32, fillcolor='rgba(46,204,113,0.08)', line_width=0, row=1, col=1)
        fig.add_hline(y=26, line=dict(color='#2ecc71', width=0.5, dash='dot'), row=1, col=1)
        fig.add_hline(y=32, line=dict(color='#2ecc71', width=0.5, dash='dot'), row=1, col=1)
        
        # OD
        fig.add_trace(go.Scatter(
            x=df_period['timestamp'], y=df_period['dissolved_oxygen'],
            mode='lines', name='OD',
            line=dict(color='#3498db', width=1.5),
            hovertemplate='%{x|%d/%m %H:%M}<br>%{y:.1f} mg/L<extra></extra>',
        ), row=2, col=1)
        fig.add_hrect(y0=4, y1=12, fillcolor='rgba(46,204,113,0.08)', line_width=0, row=2, col=1)
        fig.add_hline(y=4, line=dict(color='#f1c40f', width=0.8, dash='dash'), row=2, col=1,
                      annotation_text="Mín. ideal (4 mg/L)", annotation_position="bottom right")
        fig.add_hline(y=3, line=dict(color='#e74c3c', width=0.8, dash='dash'), row=2, col=1,
                      annotation_text="Crítico (3 mg/L)", annotation_position="bottom right")
        
        # pH
        fig.add_trace(go.Scatter(
            x=df_period['timestamp'], y=df_period['ph'],
            mode='lines', name='pH',
            line=dict(color='#9b59b6', width=1.5),
            hovertemplate='%{x|%d/%m %H:%M}<br>pH %{y:.2f}<extra></extra>',
        ), row=3, col=1)
        fig.add_hrect(y0=7.0, y1=8.5, fillcolor='rgba(46,204,113,0.08)', line_width=0, row=3, col=1)
        fig.add_hline(y=7.0, line=dict(color='#2ecc71', width=0.5, dash='dot'), row=3, col=1)
        fig.add_hline(y=8.5, line=dict(color='#2ecc71', width=0.5, dash='dot'), row=3, col=1)
        
        fig.update_layout(
            height=700,
            showlegend=False,
            plot_bgcolor='white',
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=50, r=20, t=40, b=20),
        )
        fig.update_xaxes(gridcolor='#E8E8E8', zeroline=False)
        fig.update_yaxes(gridcolor='#E8E8E8', zeroline=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        fig2 = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            subplot_titles=("Salinidade (ppt)", "TDS (ppm)")
        )
        
        fig2.add_trace(go.Scatter(
            x=df_period['timestamp'], y=df_period['salinity'],
            mode='lines', name='Salinidade',
            line=dict(color='#01696F', width=1.5),
            fill='tozeroy', fillcolor='rgba(1,105,111,0.06)',
            hovertemplate='%{x|%d/%m %H:%M}<br>%{y:.1f} ppt<extra></extra>',
        ), row=1, col=1)
        fig2.add_hrect(y0=15, y1=35, fillcolor='rgba(46,204,113,0.06)', line_width=0, row=1, col=1)
        
        fig2.add_trace(go.Scatter(
            x=df_period['timestamp'], y=df_period['tds'],
            mode='lines', name='TDS',
            line=dict(color='#e67e22', width=1.5),
            hovertemplate='%{x|%d/%m %H:%M}<br>%{y:.0f} ppm<extra></extra>',
        ), row=2, col=1)
        
        fig2.update_layout(
            height=450,
            showlegend=False,
            plot_bgcolor='white',
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=50, r=20, t=40, b=20),
        )
        fig2.update_xaxes(gridcolor='#E8E8E8')
        fig2.update_yaxes(gridcolor='#E8E8E8')
        st.plotly_chart(fig2, use_container_width=True)
    
    with tab3:
        fig3 = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            subplot_titles=("Turbidez (NTU)", "Condutividade Elétrica (µS/cm)")
        )
        
        fig3.add_trace(go.Scatter(
            x=df_period['timestamp'], y=df_period['turbidity'],
            mode='lines', name='Turbidez',
            line=dict(color='#8B4513', width=1.5),
            hovertemplate='%{x|%d/%m %H:%M}<br>%{y:.0f} NTU<extra></extra>',
        ), row=1, col=1)
        fig3.add_hrect(y0=30, y1=80, fillcolor='rgba(46,204,113,0.06)', line_width=0, row=1, col=1)
        
        fig3.add_trace(go.Scatter(
            x=df_period['timestamp'], y=df_period['electrical_conductivity'],
            mode='lines', name='EC',
            line=dict(color='#2c3e50', width=1.5),
            hovertemplate='%{x|%d/%m %H:%M}<br>%{y:.0f} µS/cm<extra></extra>',
        ), row=2, col=1)
        
        fig3.update_layout(
            height=450,
            showlegend=False,
            plot_bgcolor='white',
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=50, r=20, t=40, b=20),
        )
        fig3.update_xaxes(gridcolor='#E8E8E8')
        fig3.update_yaxes(gridcolor='#E8E8E8')
        st.plotly_chart(fig3, use_container_width=True)
    
    st.markdown("---")
    
    # --- Estatísticas do Período ---
    st.subheader("Estatísticas do Período")
    
    stats_data = []
    for param in ['temperature', 'ph', 'dissolved_oxygen', 'salinity', 'turbidity', 'tds']:
        cfg = PARAM_CONFIG[param]
        series = df_period[param].dropna()
        if series.empty:
            continue
        stats_data.append({
            'Parâmetro': f"{cfg['icon']} {cfg['label']}",
            'Mínimo': f"{series.min():{cfg['format']}} {cfg['unit']}",
            'Média': f"{series.mean():{cfg['format']}} {cfg['unit']}",
            'Máximo': f"{series.max():{cfg['format']}} {cfg['unit']}",
            'Desvio Padrão': f"{series.std():{cfg['format']}}",
            'Faixa Ideal': f"{cfg['ideal_min']} – {cfg['ideal_max'] or '∞'} {cfg['unit']}",
        })
    
    if stats_data:
        st.dataframe(pd.DataFrame(stats_data).set_index('Parâmetro'), use_container_width=True)
    
    st.markdown("---")
    
    # --- Timeline de Eventos ---
    st.subheader("Últimos Eventos de Manejo")
    
    pond_events = events[events['pond_id'] == selected_pond].head(15)
    if not pond_events.empty:
        event_icons = {
            'feeding': '🍽️', 'water_exchange': '💧', 'probiotic': '🧬',
            'aerator_on': '🔛', 'aerator_off': '⭕', 'pump_on': '🔛',
            'pump_off': '⭕', 'liming': '🪨', 'fertilization': '🌱',
        }
        
        for _, event in pond_events.iterrows():
            icon = event_icons.get(event['event_type'], '📌')
            time_str = event['timestamp'].strftime('%d/%m %H:%M')
            event_name = event['event_type'].replace('_', ' ').title()
            st.markdown(f"**{icon} {time_str}** — {event_name}: {event.get('details', '')}")
    else:
        st.info("Nenhum evento registrado para este viveiro no período.")
