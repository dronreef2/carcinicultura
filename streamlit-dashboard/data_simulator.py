"""
Gerador de dados simulados realistas para o dashboard Smart Shrimp Farm.
Simula leituras de sensores, ciclos de produção, eventos de manejo e alertas.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import uuid


def generate_sensor_data(pond_id: str, hours: int = 168, interval_min: int = 5) -> pd.DataFrame:
    """
    Gera dados de sensores simulados para um viveiro.
    Simula padrões realistas: variação diurna de OD e pH, ruído gaussiano, etc.
    
    Args:
        pond_id: Identificador do viveiro
        hours: Quantidade de horas de dados (default: 168 = 7 dias)
        interval_min: Intervalo entre leituras em minutos
    """
    np.random.seed(hash(pond_id) % 2**31)
    
    n_points = (hours * 60) // interval_min
    now = datetime.now()
    timestamps = [now - timedelta(minutes=interval_min * i) for i in range(n_points)]
    timestamps.reverse()
    
    # Hora do dia para padrões diurnos
    hour_of_day = np.array([t.hour + t.minute / 60 for t in timestamps])
    
    # --- Temperatura (°C) ---
    # Base entre 27-30°C com variação diurna de ~2°C
    temp_base = 28.5 + np.random.uniform(-0.5, 0.5)
    temp_diurnal = 1.0 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)  # Pico ~14h
    temp_trend = np.linspace(0, np.random.uniform(-0.5, 0.5), n_points)  # Tendência lenta
    temperature = temp_base + temp_diurnal + temp_trend + np.random.normal(0, 0.15, n_points)
    temperature = np.clip(temperature, 24, 35)
    
    # --- pH ---
    # Base 7.5-8.2, variação diurna (sobe à tarde por fotossíntese)
    ph_base = 7.8 + np.random.uniform(-0.2, 0.2)
    ph_diurnal = 0.3 * np.sin(2 * np.pi * (hour_of_day - 8) / 24)  # Pico ~16h
    ph = ph_base + ph_diurnal + np.random.normal(0, 0.08, n_points)
    ph = np.clip(ph, 6.5, 9.5)
    
    # --- Oxigênio Dissolvido (mg/L) ---
    # Base 5-6, CAIDE de madrugada (2-5h), sobe durante o dia
    do_base = 5.5 + np.random.uniform(-0.3, 0.3)
    do_diurnal = 1.5 * np.sin(2 * np.pi * (hour_of_day - 4) / 24)  # Mínimo ~4h madrugada
    do_noise = np.random.normal(0, 0.25, n_points)
    dissolved_oxygen = do_base + do_diurnal + do_noise
    # Simular episódios de OD baixo (3% de chance por dia)
    for day in range(hours // 24):
        if np.random.random() < 0.03:
            start = day * (1440 // interval_min) + int(3 * 60 / interval_min)  # ~3h madrugada
            end = min(start + int(2 * 60 / interval_min), n_points)  # 2h de evento
            if end <= n_points:
                dissolved_oxygen[start:end] -= np.random.uniform(1.5, 2.5)
    dissolved_oxygen = np.clip(dissolved_oxygen, 1.0, 12.0)
    
    # --- Salinidade (ppt) ---
    # Relativamente estável, com pequenas variações
    sal_base = 25 + np.random.uniform(-5, 5)
    salinity = sal_base + np.random.normal(0, 0.3, n_points)
    salinity = np.clip(salinity, 5, 45)
    
    # --- Turbidez (NTU) ---
    # Base 40-80 NTU para bioflocos, variação com alimentação
    turb_base = 60 + np.random.uniform(-15, 15)
    # Picos após horários de alimentação (6h, 11h, 17h)
    turb_feeding = np.zeros(n_points)
    for feed_hour in [6, 11, 17]:
        dist = np.abs(hour_of_day - feed_hour)
        dist = np.minimum(dist, 24 - dist)
        turb_feeding += 10 * np.exp(-dist**2 / 2)
    turbidity = turb_base + turb_feeding + np.random.normal(0, 3, n_points)
    turbidity = np.clip(turbidity, 5, 250)
    
    # --- TDS (ppm) ---
    tds = salinity * 35 + np.random.normal(0, 15, n_points)
    tds = np.clip(tds, 100, 2000)
    
    # --- Condutividade Elétrica (µS/cm) ---
    ec = tds * 1.56 + np.random.normal(0, 20, n_points)
    ec = np.clip(ec, 200, 5000)
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'pond_id': pond_id,
        'temperature': np.round(temperature, 2),
        'ph': np.round(ph, 2),
        'salinity': np.round(salinity, 2),
        'dissolved_oxygen': np.round(dissolved_oxygen, 2),
        'turbidity': np.round(turbidity, 2),
        'tds': np.round(tds, 2),
        'electrical_conductivity': np.round(ec, 2),
    })
    
    return df


def generate_ponds() -> pd.DataFrame:
    """Gera dados simulados de viveiros."""
    ponds = [
        {'id': 'P01', 'name': 'Viveiro 01', 'area_m2': 5000, 'depth_m': 1.2, 
         'system_type': 'bioflocos', 'status': 'active'},
        {'id': 'P02', 'name': 'Viveiro 02', 'area_m2': 5000, 'depth_m': 1.2, 
         'system_type': 'bioflocos', 'status': 'active'},
        {'id': 'P03', 'name': 'Viveiro 03', 'area_m2': 8000, 'depth_m': 1.0, 
         'system_type': 'tradicional', 'status': 'active'},
        {'id': 'P04', 'name': 'Viveiro 04', 'area_m2': 8000, 'depth_m': 1.0, 
         'system_type': 'tradicional', 'status': 'active'},
        {'id': 'P05', 'name': 'Viveiro 05', 'area_m2': 3000, 'depth_m': 1.5, 
         'system_type': 'raceway', 'status': 'maintenance'},
    ]
    return pd.DataFrame(ponds)


def generate_cycles() -> pd.DataFrame:
    """Gera dados simulados de ciclos de produção."""
    now = datetime.now()
    cycles = [
        {'id': 'C01', 'pond_id': 'P01', 'start_date': (now - timedelta(days=60)).date(),
         'end_date': None, 'species': 'L. vannamei', 'stocking_density': 80,
         'initial_biomass': 4.0, 'system_type': 'bioflocos', 'status': 'active', 'day': 60},
        {'id': 'C02', 'pond_id': 'P02', 'start_date': (now - timedelta(days=45)).date(),
         'end_date': None, 'species': 'L. vannamei', 'stocking_density': 80,
         'initial_biomass': 4.0, 'system_type': 'bioflocos', 'status': 'active', 'day': 45},
        {'id': 'C03', 'pond_id': 'P03', 'start_date': (now - timedelta(days=75)).date(),
         'end_date': None, 'species': 'L. vannamei', 'stocking_density': 30,
         'initial_biomass': 3.5, 'system_type': 'tradicional', 'status': 'active', 'day': 75},
        {'id': 'C04', 'pond_id': 'P04', 'start_date': (now - timedelta(days=90)).date(),
         'end_date': (now - timedelta(days=5)).date(), 'species': 'L. vannamei', 'stocking_density': 30,
         'initial_biomass': 3.5, 'system_type': 'tradicional', 'status': 'completed', 'day': 85},
        # Ciclos anteriores (finalizados) para comparação
        {'id': 'C05', 'pond_id': 'P01', 'start_date': (now - timedelta(days=180)).date(),
         'end_date': (now - timedelta(days=90)).date(), 'species': 'L. vannamei', 'stocking_density': 70,
         'initial_biomass': 3.8, 'system_type': 'bioflocos', 'status': 'completed', 'day': 90},
        {'id': 'C06', 'pond_id': 'P03', 'start_date': (now - timedelta(days=200)).date(),
         'end_date': (now - timedelta(days=110)).date(), 'species': 'L. vannamei', 'stocking_density': 25,
         'initial_biomass': 3.2, 'system_type': 'tradicional', 'status': 'completed', 'day': 90},
    ]
    return pd.DataFrame(cycles)


def generate_biometrics(cycles_df: pd.DataFrame) -> pd.DataFrame:
    """Gera dados simulados de biometrias."""
    rows = []
    now = datetime.now()
    for _, cycle in cycles_df.iterrows():
        np.random.seed(hash(cycle['id']) % 2**31)
        start = pd.Timestamp(cycle['start_date'])
        n_days = cycle['day']
        
        # Biometrias a cada ~10 dias
        for d in range(10, n_days, 10):
            # Crescimento: ~1.0-1.5 g/semana para vannamei
            growth_rate = 1.2 if cycle['system_type'] == 'bioflocos' else 1.0
            avg_weight = cycle['initial_biomass'] + (d / 7) * growth_rate * np.random.uniform(0.9, 1.1)
            survival = max(70, 95 - d * 0.15 + np.random.normal(0, 2))
            
            rows.append({
                'id': f"B{cycle['id']}_{d}",
                'cycle_id': cycle['id'],
                'pond_id': cycle['pond_id'],
                'timestamp': start + timedelta(days=d),
                'avg_weight_g': round(avg_weight, 2),
                'sample_size': np.random.randint(30, 60),
                'survival_estimate': round(min(100, survival), 1),
            })
    return pd.DataFrame(rows)


def generate_harvests(cycles_df: pd.DataFrame) -> pd.DataFrame:
    """Gera dados simulados de despescas (ciclos concluídos)."""
    rows = []
    completed = cycles_df[cycles_df['status'] == 'completed']
    for _, cycle in completed.iterrows():
        np.random.seed(hash(cycle['id']) % 2**31)
        # Produção depende do sistema
        if cycle['system_type'] == 'bioflocos':
            prod_kg_ha = np.random.uniform(3000, 5000)
            avg_weight = np.random.uniform(12, 16)
        else:
            prod_kg_ha = np.random.uniform(1000, 2500)
            avg_weight = np.random.uniform(10, 14)
        
        area_ha = 0.5 if 'P01' in cycle['pond_id'] or 'P02' in cycle['pond_id'] else 0.8
        harvest_weight = prod_kg_ha * area_ha
        survival = np.random.uniform(75, 92)
        price = np.random.uniform(25, 40)
        
        rows.append({
            'id': f"H{cycle['id']}",
            'cycle_id': cycle['id'],
            'pond_id': cycle['pond_id'],
            'timestamp': cycle['end_date'],
            'harvest_weight_kg': round(harvest_weight, 1),
            'survival_rate': round(survival, 1),
            'avg_final_weight_g': round(avg_weight, 2),
            'price_per_kg': round(price, 2),
            'total_revenue': round(harvest_weight * price, 2),
            'productivity_kg_ha': round(prod_kg_ha, 0),
        })
    return pd.DataFrame(rows)


def generate_management_events(ponds_df: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    """Gera eventos de manejo simulados."""
    rows = []
    now = datetime.now()
    active_ponds = ponds_df[ponds_df['status'] == 'active']['id'].tolist()
    
    for pond_id in active_ponds:
        np.random.seed(hash(pond_id + 'events') % 2**31)
        for d in range(days):
            dt = now - timedelta(days=d)
            
            # 3 alimentações por dia
            for hour in [6, 11, 17]:
                rows.append({
                    'timestamp': dt.replace(hour=hour, minute=np.random.randint(0, 30)),
                    'pond_id': pond_id,
                    'event_type': 'feeding',
                    'details': f'{np.random.uniform(3, 8):.1f} kg'
                })
            
            # Troca de água (a cada 3-4 dias)
            if d % np.random.choice([3, 4]) == 0:
                rows.append({
                    'timestamp': dt.replace(hour=8, minute=0),
                    'pond_id': pond_id,
                    'event_type': 'water_exchange',
                    'details': f'{np.random.randint(5, 15)}% do volume'
                })
            
            # Aerador liga/desliga (eventos automáticos)
            if np.random.random() < 0.3:
                rows.append({
                    'timestamp': dt.replace(hour=3, minute=np.random.randint(0, 59)),
                    'pond_id': pond_id,
                    'event_type': 'aerator_on',
                    'details': 'OD baixo - acionamento automático'
                })
                rows.append({
                    'timestamp': dt.replace(hour=5, minute=np.random.randint(0, 59)),
                    'pond_id': pond_id,
                    'event_type': 'aerator_off',
                    'details': 'OD normalizado'
                })
    
    return pd.DataFrame(rows).sort_values('timestamp', ascending=False).reset_index(drop=True)


def generate_alerts(sensor_data: dict) -> pd.DataFrame:
    """Gera alertas baseados em dados de sensores."""
    rows = []
    
    THRESHOLDS = {
        'temperature': {'warning_min': 26, 'warning_max': 32, 'critical_min': 24, 'critical_max': 34, 'unit': '°C'},
        'ph': {'warning_min': 7.0, 'warning_max': 8.5, 'critical_min': 6.5, 'critical_max': 9.5, 'unit': ''},
        'dissolved_oxygen': {'warning_min': 4.0, 'warning_max': None, 'critical_min': 3.0, 'critical_max': None, 'unit': 'mg/L'},
        'salinity': {'warning_min': 15, 'warning_max': 35, 'critical_min': 5, 'critical_max': 45, 'unit': 'ppt'},
    }
    
    for pond_id, df in sensor_data.items():
        last_24h = df[df['timestamp'] >= datetime.now() - timedelta(hours=24)]
        
        for param, limits in THRESHOLDS.items():
            if param not in last_24h.columns:
                continue
            values = last_24h[param].dropna()
            if values.empty:
                continue
            
            current = values.iloc[-1]
            
            if limits.get('critical_min') and current < limits['critical_min']:
                rows.append({
                    'timestamp': last_24h['timestamp'].iloc[-1],
                    'pond_id': pond_id,
                    'alert_type': f'{param}_critical_low',
                    'severity': 'critical',
                    'parameter': param,
                    'value': round(current, 2),
                    'threshold': limits['critical_min'],
                    'message': f'{param.replace("_", " ").title()} em {current:.1f}{limits["unit"]} — abaixo do limite crítico ({limits["critical_min"]}{limits["unit"]})',
                    'handled': False,
                })
            elif limits.get('critical_max') and current > limits['critical_max']:
                rows.append({
                    'timestamp': last_24h['timestamp'].iloc[-1],
                    'pond_id': pond_id,
                    'alert_type': f'{param}_critical_high',
                    'severity': 'critical',
                    'parameter': param,
                    'value': round(current, 2),
                    'threshold': limits['critical_max'],
                    'message': f'{param.replace("_", " ").title()} em {current:.1f}{limits["unit"]} — acima do limite crítico ({limits["critical_max"]}{limits["unit"]})',
                    'handled': False,
                })
            elif limits.get('warning_min') and current < limits['warning_min']:
                rows.append({
                    'timestamp': last_24h['timestamp'].iloc[-1],
                    'pond_id': pond_id,
                    'alert_type': f'{param}_warning_low',
                    'severity': 'warning',
                    'parameter': param,
                    'value': round(current, 2),
                    'threshold': limits['warning_min'],
                    'message': f'{param.replace("_", " ").title()} em {current:.1f}{limits["unit"]} — abaixo do ideal ({limits["warning_min"]}{limits["unit"]})',
                    'handled': False,
                })
            elif limits.get('warning_max') and current > limits['warning_max']:
                rows.append({
                    'timestamp': last_24h['timestamp'].iloc[-1],
                    'pond_id': pond_id,
                    'alert_type': f'{param}_warning_high',
                    'severity': 'warning',
                    'parameter': param,
                    'value': round(current, 2),
                    'threshold': limits['warning_max'],
                    'message': f'{param.replace("_", " ").title()} em {current:.1f}{limits["unit"]} — acima do ideal ({limits["warning_max"]}{limits["unit"]})',
                    'handled': False,
                })
    
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        'timestamp', 'pond_id', 'alert_type', 'severity', 'parameter', 'value', 'threshold', 'message', 'handled'
    ])


# ============================================================================
# Faixas de referência para display
# ============================================================================
PARAM_CONFIG = {
    'temperature': {
        'label': 'Temperatura',
        'unit': '°C',
        'icon': '🌡️',
        'ideal_min': 26, 'ideal_max': 32,
        'warning_min': 24, 'warning_max': 34,
        'format': '.1f',
    },
    'ph': {
        'label': 'pH',
        'unit': '',
        'icon': '🧪',
        'ideal_min': 7.0, 'ideal_max': 8.5,
        'warning_min': 6.5, 'warning_max': 9.5,
        'format': '.2f',
    },
    'dissolved_oxygen': {
        'label': 'Oxigênio Dissolvido',
        'unit': 'mg/L',
        'icon': '💨',
        'ideal_min': 4.0, 'ideal_max': 12.0,
        'warning_min': 3.0, 'warning_max': None,
        'format': '.1f',
    },
    'salinity': {
        'label': 'Salinidade',
        'unit': 'ppt',
        'icon': '🧂',
        'ideal_min': 15, 'ideal_max': 35,
        'warning_min': 5, 'warning_max': 45,
        'format': '.1f',
    },
    'turbidity': {
        'label': 'Turbidez',
        'unit': 'NTU',
        'icon': '🌊',
        'ideal_min': 30, 'ideal_max': 80,
        'warning_min': 10, 'warning_max': 200,
        'format': '.0f',
    },
    'tds': {
        'label': 'TDS',
        'unit': 'ppm',
        'icon': '📊',
        'ideal_min': 500, 'ideal_max': 1500,
        'warning_min': 100, 'warning_max': 2000,
        'format': '.0f',
    },
}


def get_status_color(value: float, param: str) -> str:
    """Retorna cor do semáforo baseado no valor e parâmetro."""
    cfg = PARAM_CONFIG.get(param)
    if cfg is None:
        return 'gray'
    
    if cfg['ideal_min'] <= value <= (cfg['ideal_max'] or float('inf')):
        return 'green'
    elif (cfg.get('warning_min') and value < cfg['warning_min']) or \
         (cfg.get('warning_max') and value > cfg['warning_max']):
        return 'red'
    else:
        return 'orange'


def get_status_emoji(value: float, param: str) -> str:
    """Retorna emoji de semáforo."""
    color = get_status_color(value, param)
    return {'green': '🟢', 'orange': '🟡', 'red': '🔴'}.get(color, '⚪')
