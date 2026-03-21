"""
Página: Estudos de Produção
Comparação de ciclos, curvas de crescimento, produtividade e análise de manejo.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from data_simulator import PARAM_CONFIG


def render(data: dict):
    st.markdown("""
    <div class="main-header">
        <h1>📈 Estudos de Produção</h1>
        <p>Análise de ciclos, crescimento e produtividade dos viveiros</p>
    </div>
    """, unsafe_allow_html=True)
    
    cycles = data['cycles']
    biometrics = data['biometrics']
    harvests = data['harvests']
    sensor_data = data['sensor_data']
    
    # --- Tabs ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Visão Geral dos Ciclos",
        "📈 Curvas de Crescimento",
        "🏆 Produtividade",
        "🔬 Correlações"
    ])
    
    # ========================================================================
    # Tab 1: Visão Geral dos Ciclos
    # ========================================================================
    with tab1:
        st.subheader("Ciclos de Produção")
        
        cycle_display = []
        for _, c in cycles.iterrows():
            status_icon = '🟢' if c['status'] == 'active' else '✅' if c['status'] == 'completed' else '❌'
            
            # Buscar última biometria
            bio = biometrics[biometrics['cycle_id'] == c['id']]
            last_weight = f"{bio.iloc[-1]['avg_weight_g']:.1f} g" if not bio.empty else "—"
            last_survival = f"{bio.iloc[-1]['survival_estimate']:.0f}%" if not bio.empty else "—"
            
            # Buscar colheita
            harv = harvests[harvests['cycle_id'] == c['id']]
            harvest_info = f"{harv.iloc[0]['harvest_weight_kg']:.0f} kg" if not harv.empty else "—"
            revenue = f"R$ {harv.iloc[0]['total_revenue']:,.2f}" if not harv.empty else "—"
            
            cycle_display.append({
                'Status': f"{status_icon} {c['status'].title()}",
                'Ciclo': c['id'],
                'Viveiro': c['pond_id'],
                'Sistema': c['system_type'].title(),
                'Início': c['start_date'],
                'Dia': c['day'],
                'Densidade (cam/m²)': c['stocking_density'],
                'Último Peso': last_weight,
                'Sobrevivência': last_survival,
                'Colheita': harvest_info,
                'Receita': revenue,
            })
        
        st.dataframe(
            pd.DataFrame(cycle_display),
            use_container_width=True,
            hide_index=True,
        )
        
        # KPIs de ciclos concluídos
        completed = cycles[cycles['status'] == 'completed']
        if not harvests.empty:
            st.markdown("---")
            st.subheader("Resumo de Ciclos Concluídos")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Colhido", f"{harvests['harvest_weight_kg'].sum():,.0f} kg")
            with col2:
                st.metric("Receita Total", f"R$ {harvests['total_revenue'].sum():,.2f}")
            with col3:
                avg_survival = harvests['survival_rate'].mean()
                st.metric("Sobrevivência Média", f"{avg_survival:.1f}%")
            with col4:
                avg_prod = harvests['productivity_kg_ha'].mean() if 'productivity_kg_ha' in harvests.columns else 0
                st.metric("Produtividade Média", f"{avg_prod:,.0f} kg/ha")
    
    # ========================================================================
    # Tab 2: Curvas de Crescimento
    # ========================================================================
    with tab2:
        st.subheader("Curvas de Crescimento por Ciclo")
        
        if biometrics.empty:
            st.info("Nenhum dado de biometria disponível.")
        else:
            # Seletor de ciclos
            cycle_ids = biometrics['cycle_id'].unique().tolist()
            selected_cycles = st.multiselect(
                "Selecione ciclos para comparar",
                cycle_ids,
                default=cycle_ids[:3]
            )
            
            if selected_cycles:
                fig = go.Figure()
                
                colors = ['#01696F', '#e74c3c', '#3498db', '#f1c40f', '#9b59b6', '#e67e22']
                
                for i, cycle_id in enumerate(selected_cycles):
                    bio = biometrics[biometrics['cycle_id'] == cycle_id].sort_values('timestamp')
                    cycle_info = cycles[cycles['id'] == cycle_id].iloc[0]
                    
                    # Calcular dia do ciclo
                    start = pd.Timestamp(cycle_info['start_date'])
                    days = [(pd.Timestamp(t) - start).days for t in bio['timestamp']]
                    
                    color = colors[i % len(colors)]
                    
                    fig.add_trace(go.Scatter(
                        x=days,
                        y=bio['avg_weight_g'],
                        mode='lines+markers',
                        name=f"{cycle_id} ({cycle_info['pond_id']} · {cycle_info['system_type']})",
                        line=dict(color=color, width=2),
                        marker=dict(size=8),
                        hovertemplate=(
                            f"Ciclo {cycle_id}<br>"
                            "Dia %{x}<br>"
                            "Peso: %{y:.1f} g<extra></extra>"
                        ),
                    ))
                
                fig.update_layout(
                    title="Ganho de Peso ao Longo do Ciclo",
                    xaxis_title="Dia do Ciclo",
                    yaxis_title="Peso Médio (g)",
                    height=450,
                    plot_bgcolor='white',
                    paper_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation='h', yanchor='bottom', y=1.02),
                    margin=dict(l=50, r=20, t=60, b=50),
                )
                fig.update_xaxes(gridcolor='#E8E8E8')
                fig.update_yaxes(gridcolor='#E8E8E8')
                st.plotly_chart(fig, use_container_width=True)
                
                # Curva de sobrevivência
                fig_surv = go.Figure()
                for i, cycle_id in enumerate(selected_cycles):
                    bio = biometrics[biometrics['cycle_id'] == cycle_id].sort_values('timestamp')
                    cycle_info = cycles[cycles['id'] == cycle_id].iloc[0]
                    start = pd.Timestamp(cycle_info['start_date'])
                    days = [(pd.Timestamp(t) - start).days for t in bio['timestamp']]
                    
                    fig_surv.add_trace(go.Scatter(
                        x=days,
                        y=bio['survival_estimate'],
                        mode='lines+markers',
                        name=f"{cycle_id}",
                        line=dict(color=colors[i % len(colors)], width=2),
                        marker=dict(size=6),
                    ))
                
                fig_surv.update_layout(
                    title="Sobrevivência Estimada ao Longo do Ciclo",
                    xaxis_title="Dia do Ciclo",
                    yaxis_title="Sobrevivência (%)",
                    height=350,
                    plot_bgcolor='white',
                    paper_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation='h', yanchor='bottom', y=1.02),
                    margin=dict(l=50, r=20, t=60, b=50),
                    yaxis=dict(range=[60, 100]),
                )
                fig_surv.update_xaxes(gridcolor='#E8E8E8')
                fig_surv.update_yaxes(gridcolor='#E8E8E8')
                st.plotly_chart(fig_surv, use_container_width=True)
    
    # ========================================================================
    # Tab 3: Produtividade
    # ========================================================================
    with tab3:
        st.subheader("Comparação de Produtividade")
        
        if harvests.empty:
            st.info("Nenhuma despesca registrada ainda.")
        else:
            # Gráfico de barras: produtividade por ciclo
            fig_prod = go.Figure()
            
            for _, h in harvests.iterrows():
                cycle_info = cycles[cycles['id'] == h['cycle_id']].iloc[0]
                color = '#01696F' if cycle_info['system_type'] == 'bioflocos' else '#e67e22'
                
                fig_prod.add_trace(go.Bar(
                    x=[f"{h['cycle_id']}<br>({cycle_info['pond_id']})"],
                    y=[h['productivity_kg_ha']],
                    name=cycle_info['system_type'].title(),
                    marker_color=color,
                    text=f"{h['productivity_kg_ha']:,.0f}",
                    textposition='outside',
                    hovertemplate=(
                        f"Ciclo: {h['cycle_id']}<br>"
                        f"Viveiro: {cycle_info['pond_id']}<br>"
                        f"Sistema: {cycle_info['system_type']}<br>"
                        f"Produtividade: {h['productivity_kg_ha']:,.0f} kg/ha<br>"
                        f"Receita: R$ {h['total_revenue']:,.2f}<extra></extra>"
                    ),
                ))
            
            fig_prod.update_layout(
                title="Produtividade por Ciclo (kg/ha)",
                yaxis_title="kg/ha",
                height=400,
                showlegend=False,
                plot_bgcolor='white',
                paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=50, r=20, t=60, b=50),
            )
            fig_prod.update_xaxes(gridcolor='#E8E8E8')
            fig_prod.update_yaxes(gridcolor='#E8E8E8')
            st.plotly_chart(fig_prod, use_container_width=True)
            
            # Tabela comparativa
            st.subheader("Tabela Comparativa")
            comp_data = []
            for _, h in harvests.iterrows():
                cycle_info = cycles[cycles['id'] == h['cycle_id']].iloc[0]
                comp_data.append({
                    'Ciclo': h['cycle_id'],
                    'Viveiro': cycle_info['pond_id'],
                    'Sistema': cycle_info['system_type'].title(),
                    'Dias': cycle_info['day'],
                    'Densidade (cam/m²)': cycle_info['stocking_density'],
                    'Colheita (kg)': f"{h['harvest_weight_kg']:,.1f}",
                    'Peso Final (g)': f"{h['avg_final_weight_g']:.1f}",
                    'Sobrevivência (%)': f"{h['survival_rate']:.1f}",
                    'Produtividade (kg/ha)': f"{h['productivity_kg_ha']:,.0f}",
                    'Preço (R$/kg)': f"{h['price_per_kg']:.2f}",
                    'Receita (R$)': f"{h['total_revenue']:,.2f}",
                })
            
            st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)
    
    # ========================================================================
    # Tab 4: Correlações
    # ========================================================================
    with tab4:
        st.subheader("Correlação: Qualidade da Água vs. Crescimento")
        
        st.markdown("""
        Análise exploratória da relação entre parâmetros de água e desempenho do ciclo.
        Com dados reais acumulados, esses gráficos ajudam a identificar padrões e otimizar o manejo.
        """)
        
        # Scatter: temperatura média vs. crescimento
        if not biometrics.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                param_x = st.selectbox(
                    "Parâmetro do eixo X",
                    ['temperature', 'ph', 'dissolved_oxygen', 'salinity', 'turbidity'],
                    format_func=lambda x: PARAM_CONFIG[x]['label']
                )
            with col2:
                param_y = st.selectbox(
                    "Métrica do eixo Y",
                    ['avg_weight_g', 'survival_estimate'],
                    format_func=lambda x: {'avg_weight_g': 'Peso Médio (g)', 'survival_estimate': 'Sobrevivência (%)'}[x]
                )
            
            # Para cada biometria, calcular média do parâmetro nos 10 dias anteriores
            corr_data = []
            for _, bio in biometrics.iterrows():
                pond_id = bio.get('pond_id')
                if pond_id and pond_id in sensor_data:
                    df = sensor_data[pond_id]
                    # Janela de 10 dias antes da biometria
                    window = df[
                        (df['timestamp'] >= bio['timestamp'] - pd.Timedelta(days=10)) &
                        (df['timestamp'] <= bio['timestamp'])
                    ]
                    if not window.empty and param_x in window.columns:
                        corr_data.append({
                            'param_value': window[param_x].mean(),
                            'metric_value': bio[param_y],
                            'cycle_id': bio['cycle_id'],
                            'pond_id': pond_id,
                        })
            
            if corr_data:
                corr_df = pd.DataFrame(corr_data)
                
                fig_corr = px.scatter(
                    corr_df,
                    x='param_value',
                    y='metric_value',
                    color='cycle_id',
                    labels={
                        'param_value': f"{PARAM_CONFIG[param_x]['label']} (média 10d)",
                        'metric_value': {'avg_weight_g': 'Peso Médio (g)', 'survival_estimate': 'Sobrevivência (%)'}[param_y],
                        'cycle_id': 'Ciclo',
                    },
                    trendline='ols',
                    height=450,
                    color_discrete_sequence=['#01696F', '#e74c3c', '#3498db', '#f1c40f', '#9b59b6'],
                )
                fig_corr.update_layout(
                    plot_bgcolor='white',
                    paper_bgcolor='rgba(0,0,0,0)',
                )
                fig_corr.update_xaxes(gridcolor='#E8E8E8')
                fig_corr.update_yaxes(gridcolor='#E8E8E8')
                st.plotly_chart(fig_corr, use_container_width=True)
            else:
                st.info("Dados insuficientes para gerar correlação. Mais dados de biometria são necessários.")
        else:
            st.info("Nenhum dado de biometria disponível para análise de correlação.")
