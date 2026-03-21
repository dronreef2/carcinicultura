"""
Página: Alertas e Eventos
Alertas ativos, histórico de eventos e controle de atuadores.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from data_simulator import PARAM_CONFIG


def render(data: dict):
    st.markdown("""
    <div class="main-header">
        <h1>🚨 Alertas e Eventos</h1>
        <p>Alertas do sistema, histórico de eventos e controle de atuadores</p>
    </div>
    """, unsafe_allow_html=True)
    
    alerts = data['alerts']
    events = data['events']
    ponds = data['ponds']
    sensor_data = data['sensor_data']
    
    # --- Tabs ---
    tab1, tab2, tab3 = st.tabs(["🚨 Alertas Ativos", "📋 Histórico de Eventos", "🎛️ Controle de Atuadores"])
    
    # ========================================================================
    # Tab 1: Alertas Ativos
    # ========================================================================
    with tab1:
        if alerts.empty:
            st.success("✅ Nenhum alerta ativo. Todos os parâmetros estão nas faixas ideais.")
        else:
            # Resumo
            n_critical = len(alerts[alerts['severity'] == 'critical'])
            n_warning = len(alerts[alerts['severity'] == 'warning'])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total de Alertas", len(alerts))
            with col2:
                if n_critical > 0:
                    st.metric("Críticos", n_critical, delta_color="inverse")
                else:
                    st.metric("Críticos", 0)
            with col3:
                st.metric("Atenção", n_warning)
            
            st.markdown("---")
            
            # Lista de alertas
            # Críticos primeiro
            sorted_alerts = alerts.sort_values(
                by=['severity', 'timestamp'],
                key=lambda x: x.map({'critical': 0, 'warning': 1, 'info': 2}) if x.name == 'severity' else x,
                ascending=[True, False]
            )
            
            for _, alert in sorted_alerts.iterrows():
                severity = alert['severity']
                css_class = 'alert-critical' if severity == 'critical' else 'alert-warning'
                icon = '🔴' if severity == 'critical' else '🟡'
                
                pond_name = ponds[ponds['id'] == alert['pond_id']]['name'].values
                pond_display = pond_name[0] if len(pond_name) > 0 else alert['pond_id']
                
                time_str = alert['timestamp'].strftime('%d/%m/%Y %H:%M') if pd.notna(alert['timestamp']) else '--'
                
                st.markdown(f"""
                <div class="{css_class}">
                    <strong>{icon} {severity.upper()}</strong> — {pond_display} · {time_str}<br>
                    {alert['message']}
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # --- Faixas de referência ---
        st.subheader("📋 Faixas de Referência para L. vannamei")
        
        ref_data = []
        for param, cfg in PARAM_CONFIG.items():
            ref_data.append({
                'Parâmetro': f"{cfg['icon']} {cfg['label']}",
                'Unidade': cfg['unit'],
                'Faixa Ideal': f"{cfg['ideal_min']} – {cfg['ideal_max'] or '∞'}",
                'Limite Alerta': f"< {cfg.get('warning_min', '—')} ou > {cfg.get('warning_max') or '∞'}",
            })
        
        st.dataframe(pd.DataFrame(ref_data), use_container_width=True, hide_index=True)
    
    # ========================================================================
    # Tab 2: Histórico de Eventos
    # ========================================================================
    with tab2:
        st.subheader("Histórico de Eventos de Manejo")
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        with col1:
            active_ponds = ponds[ponds['status'] == 'active']
            filter_pond = st.selectbox(
                "Viveiro",
                ["Todos"] + active_ponds['id'].tolist(),
                format_func=lambda x: "Todos os viveiros" if x == "Todos" else 
                    f"{ponds[ponds['id'] == x]['name'].values[0]} ({x})"
            )
        with col2:
            event_types = events['event_type'].unique().tolist() if not events.empty else []
            filter_type = st.selectbox(
                "Tipo de Evento",
                ["Todos"] + sorted(event_types),
                format_func=lambda x: "Todos os tipos" if x == "Todos" else x.replace('_', ' ').title()
            )
        with col3:
            filter_days = st.selectbox("Período", [1, 3, 7], index=2, format_func=lambda x: f"Últimos {x} dia(s)")
        
        # Aplicar filtros
        filtered = events.copy()
        if filter_pond != "Todos":
            filtered = filtered[filtered['pond_id'] == filter_pond]
        if filter_type != "Todos":
            filtered = filtered[filtered['event_type'] == filter_type]
        filtered = filtered[filtered['timestamp'] >= datetime.now() - timedelta(days=filter_days)]
        
        if filtered.empty:
            st.info("Nenhum evento encontrado com os filtros selecionados.")
        else:
            st.markdown(f"**{len(filtered)} eventos encontrados**")
            
            event_icons = {
                'feeding': '🍽️', 'water_exchange': '💧', 'probiotic': '🧬',
                'aerator_on': '🔛', 'aerator_off': '⭕', 'pump_on': '🔛',
                'pump_off': '⭕', 'liming': '🪨', 'fertilization': '🌱',
            }
            
            display_events = []
            for _, event in filtered.iterrows():
                icon = event_icons.get(event['event_type'], '📌')
                pond_name = ponds[ponds['id'] == event['pond_id']]['name'].values
                display_events.append({
                    'Data/Hora': event['timestamp'].strftime('%d/%m %H:%M'),
                    'Viveiro': pond_name[0] if len(pond_name) > 0 else event['pond_id'],
                    'Tipo': f"{icon} {event['event_type'].replace('_', ' ').title()}",
                    'Detalhes': event.get('details', ''),
                })
            
            st.dataframe(
                pd.DataFrame(display_events),
                use_container_width=True,
                hide_index=True,
            )
            
            # Gráfico: contagem de eventos por tipo
            st.markdown("---")
            st.subheader("Distribuição de Eventos")
            
            event_counts = filtered.groupby('event_type').size().reset_index(name='count')
            event_counts = event_counts.sort_values('count', ascending=True)
            
            fig = go.Figure(go.Bar(
                x=event_counts['count'],
                y=event_counts['event_type'].apply(lambda x: x.replace('_', ' ').title()),
                orientation='h',
                marker_color='#01696F',
                text=event_counts['count'],
                textposition='outside',
            ))
            fig.update_layout(
                height=300,
                plot_bgcolor='white',
                paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=120, r=20, t=20, b=20),
                xaxis_title="Quantidade",
            )
            fig.update_xaxes(gridcolor='#E8E8E8')
            st.plotly_chart(fig, use_container_width=True)
    
    # ========================================================================
    # Tab 3: Controle de Atuadores
    # ========================================================================
    with tab3:
        st.subheader("Painel de Controle de Atuadores")
        st.caption("⚠️ Modo de simulação — comandos não são enviados ao hardware real")
        
        active_ponds_list = ponds[ponds['status'] == 'active']
        
        for _, pond in active_ponds_list.iterrows():
            with st.container(border=True):
                st.markdown(f"### {pond['name']} ({pond['id']})")
                
                col1, col2, col3 = st.columns(3)
                
                # Aerador
                with col1:
                    st.markdown("**💨 Aerador**")
                    aerator_state = st.toggle(
                        "Ligar Aerador",
                        value=False,
                        key=f"aerator_{pond['id']}"
                    )
                    if aerator_state:
                        st.success("🟢 LIGADO")
                    else:
                        st.markdown("⚪ Desligado")
                    st.caption("Auto: OD < 4 mg/L → Liga")
                
                # Bomba
                with col2:
                    st.markdown("**💧 Bomba de Água**")
                    pump_state = st.toggle(
                        "Ligar Bomba",
                        value=False,
                        key=f"pump_{pond['id']}"
                    )
                    if pump_state:
                        st.success("🟢 LIGADO")
                    else:
                        st.markdown("⚪ Desligado")
                    st.caption("Renovação parcial de água")
                
                # Alimentador
                with col3:
                    st.markdown("**🍽️ Alimentador**")
                    if st.button("Acionar Alimentação", key=f"feed_{pond['id']}"):
                        st.success("✅ Alimentação acionada (simulação)")
                    st.caption("Próx. alimentação: 17:00")
                
                # Mostrar OD atual se disponível
                if pond['id'] in sensor_data:
                    latest = sensor_data[pond['id']].iloc[-1]
                    do_val = latest.get('dissolved_oxygen')
                    if do_val is not None:
                        color = '#2ecc71' if do_val >= 4 else '#f1c40f' if do_val >= 3 else '#e74c3c'
                        st.markdown(f"OD atual: **{do_val:.1f} mg/L** <span style='color:{color}'>●</span>", unsafe_allow_html=True)
        
        st.markdown("---")
        st.info("""
        **Regras de automação configuradas:**
        - Aerador liga automaticamente se OD < 4 mg/L
        - Aerador desliga após OD > 6 mg/L por 20+ minutos
        - Alimentação programada: 06:00, 11:00, 17:00
        - Bomba: acionamento manual ou por condição composta (turbidez + OD + pH)
        """)
