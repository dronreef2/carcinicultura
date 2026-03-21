"""
Calculadora simples de ROI para proposta comercial Smart Shrimp Farm.

Uso:
  python docs/comercial/calculadora-roi.py \
    --viveiros 3 \
    --biomassa-kg 20000 \
    --preco-kg 25 \
    --perda-evitada-pct 5 \
    --ganho-kg-ha 200 \
    --area-ha 0.5 \
    --setup 4500 \
    --mensalidade 390 \
    --meses 6
"""

import argparse


def calcular(args):
    receita_protegida = args.viveiros * args.biomassa_kg * args.preco_kg * (args.perda_evitada_pct / 100.0)
    ganho_produtividade = args.viveiros * args.ganho_kg_ha * args.area_ha * args.preco_kg
    beneficio_total = receita_protegida + ganho_produtividade

    custo_setup = args.viveiros * args.setup
    custo_saas = args.viveiros * args.mensalidade * args.meses
    custo_total = custo_setup + custo_saas

    roi = ((beneficio_total - custo_total) / custo_total) if custo_total > 0 else 0.0

    beneficio_mensal = beneficio_total / args.meses if args.meses > 0 else 0.0
    payback_meses = (custo_setup / beneficio_mensal) if beneficio_mensal > 0 else None

    return {
        "receita_protegida": receita_protegida,
        "ganho_produtividade": ganho_produtividade,
        "beneficio_total": beneficio_total,
        "custo_setup": custo_setup,
        "custo_saas": custo_saas,
        "custo_total": custo_total,
        "roi": roi,
        "payback_meses": payback_meses,
    }


def moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    parser = argparse.ArgumentParser(description="Calculadora de ROI comercial")
    parser.add_argument("--viveiros", type=int, required=True)
    parser.add_argument("--biomassa-kg", type=float, required=True)
    parser.add_argument("--preco-kg", type=float, required=True)
    parser.add_argument("--perda-evitada-pct", type=float, required=True)
    parser.add_argument("--ganho-kg-ha", type=float, default=0.0)
    parser.add_argument("--area-ha", type=float, default=0.0)
    parser.add_argument("--setup", type=float, required=True)
    parser.add_argument("--mensalidade", type=float, required=True)
    parser.add_argument("--meses", type=int, required=True)

    args = parser.parse_args()
    r = calcular(args)

    print("=== Resultado comercial ===")
    print(f"Receita protegida: {moeda(r['receita_protegida'])}")
    print(f"Ganho por produtividade: {moeda(r['ganho_produtividade'])}")
    print(f"Beneficio total: {moeda(r['beneficio_total'])}")
    print(f"Custo setup: {moeda(r['custo_setup'])}")
    print(f"Custo SaaS ({args.meses} meses): {moeda(r['custo_saas'])}")
    print(f"Custo total: {moeda(r['custo_total'])}")
    print(f"ROI: {r['roi'] * 100:.2f}%")
    if r["payback_meses"] is not None:
        print(f"Payback setup: {r['payback_meses']:.2f} meses")
    else:
        print("Payback setup: nao calculavel")


if __name__ == "__main__":
    main()
