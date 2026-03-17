"""
Página: Visão Geral dos Viveiros
Mostra todos os viveiros com semáforo de status e resumo de parâmetros.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from data_simulator import PARAM_CONFIG, get_status_emoji, get_status_color


def render(data: dict):
    st.markdown("""
    <div class="main-header">
        <h1>📊 Visão Geral dos Viveiros</h1>
        <p>Monitoramento em tempo real de todos os viveiros da fazenda</p>
    </div>
    """, unsafe_allow_html=True)
    
    ponds = data['ponds']
    sensor_data = data['sensor_data']
    cycles = data['cycles']
    alerts = data['alerts']
    
    # --- KPIs Globais ---
    col1, col2, col3, col4 = st.columns(4)
    
    active_ponds = ponds[ponds['status'] == 'active']
    active_cycles = cycles[cycles['status'] == 'active']
    n_critical = len(alerts[alerts['severity'] == 'critical']) if not alerts.empty else 0
    n_warning = len(alerts[alerts['severity'] == 'warning']) if not alerts.empty else 0
    
    with col1:
        st.metric("Viveiros Ativos", len(active_ponds), f"de {len(ponds)} total")
    with col2:
        st.metric("Ciclos em Andamento", len(active_cycles))
    with col3:
        st.metric("Alertas Críticos", n_critical, delta_color="inverse")
    with col4:
        st.metric("Alertas de Atenção", n_warning, delta_color="inverse")
    
    st.markdown("---")
    
    # --- Cards dos Viveiros ---
    st.subheader("Status dos Viveiros")
    
    # 2 viveiros por linha
    pond_list = ponds.to_dict('records')
    for i in range(0, len(pond_list), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(pond_list):
                break
            
            pond = pond_list[idx]
            pond_id = pond['id']
            
            with col:
                # Determinar status geral
                if pond['status'] != 'active':
                    overall_status = '⚪ Inativo'
                    border_color = '#BAB9B4'
                elif pond_id in sensor_data:
                    df = sensor_data[pond_id]
                    latest = df.iloc[-1]
                    statuses = []
                    for param in ['temperature', 'ph', 'dissolved_oxygen', 'salinity']:
                        if param in latest and pd.notna(latest[param]):
                            statuses.append(get_status_color(latest[param], param))
                    
                    if 'red' in statuses:
                        overall_status = '🔴 Crítico'
                        border_color = '#e74c3c'
                    elif 'orange' in statuses:
                        overall_status = '🟡 Atenção'
                        border_color = '#f1c40f'
                    else:
                        overall_status = '🟢 Normal'
                        border_color = '#2ecc71'
                else:
                    overall_status = '⚪ Sem dados'
                    border_color = '#BAB9B4'
                
                # Encontrar ciclo ativo
                cycle_info = cycles[(cycles['pond_id'] == pond_id) & (cycles['status'] == 'active')]
                
                with st.container(border=True):
                    # Header do card
                    header_col1, header_col2 = st.columns([3, 1])
                    with header_col1:
                        st.markdown(f"### {pond['name']}")
                    with header_col2:
                        st.markdown(f"**{overall_status}**")
                    
                    st.caption(f"📐 {pond['area_m2']:,.0f} m² · 🌊 {pond['depth_m']}m · 🏷️ {pond['system_type'].title()}")
                    
                    if not cycle_info.empty:
                        c = cycle_info.iloc[0]
                        st.caption(f"📅 Ciclo dia {c['day']} · Densidade: {c['stocking_density']} cam/m²")
                    
                    if pond['status'] == 'active' and pond_id in sensor_data:
                        df = sensor_data[pond_id]
                        latest = df.iloc[-1]
                        
                        # Parâmetros em grade
                        params = ['temperature', 'ph', 'dissolved_oxygen', 'salinity', 'turbidity', 'tds']
                        p_cols = st.columns(3)
                        
                        for k, param in enumerate(params):
                            cfg = PARAM_CONFIG[param]
                            val = latest.get(param)
                            if val is not None and pd.notna(val):
                                emoji = get_status_emoji(val, param)
                                with p_cols[k % 3]:
                                    st.markdown(
                                        f"**{cfg['icon']} {cfg['label']}**  \n"
                                        f"{emoji} {val:{cfg['format']}} {cfg['unit']}"
                                    )
                        
                        # Mini sparkline de temperatura (últimas 24h)
                        last_24h = df[df['timestamp'] >= datetime.now() - timedelta(hours=24)]
                        if not last_24h.empty:
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=last_24h['timestamp'],
                                y=last_24h['temperature'],
                                mode='lines',
                                line=dict(color='#01696F', width=1.5),
                                fill='tozeroy',
                                fillcolor='rgba(1,105,111,0.08)',
                                hovertemplate='%{x|%H:%M}<br>%{y:.1f}°C<extra></extra>',
                            ))
                            fig.update_layout(
                                height=100,
                                margin=dict(l=0, r=0, t=0, b=0),
                                xaxis=dict(visible=False),
                                yaxis=dict(visible=False),
                                showlegend=False,
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='rgba(0,0,0,0)',
                            )
                            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                    elif pond['status'] != 'active':
                        st.info(f"Viveiro em {pond['status']}")
    
    st.markdown("---")
    
    # --- Mapa de calor: parâmetros por viveiro ---
    st.subheader("Mapa de Parâmetros (Últimas Leituras)")
    
    heatmap_data = []
    for _, pond in active_ponds.iterrows():
        pid = pond['id']
        if pid in sensor_data:
            latest = sensor_data[pid].iloc[-1]
            row = {'Viveiro': pond['name']}
            for param in ['temperature', 'ph', 'dissolved_oxygen', 'salinity', 'turbidity']:
                cfg = PARAM_CONFIG[param]
                val = latest.get(param)
                if val is not None and pd.notna(val):
                    emoji = get_status_emoji(val, param)
                    row[f"{cfg['icon']} {cfg['label']}"] = f"{emoji} {val:{cfg['format']}} {cfg['unit']}"
            heatmap_data.append(row)
    
    if heatmap_data:
        st.dataframe(
            pd.DataFrame(heatmap_data).set_index('Viveiro'),
            use_container_width=True,
        )
