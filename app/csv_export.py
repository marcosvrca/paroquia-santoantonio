import csv
import io
import re
import unicodedata
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models import (
    DiaFestejo,
    LeilaoMovimento,
    NotaFiscal,
    RifaMovimento,
    Sangria,
)
from app.services import (
    is_nota_manual,
    listar_caixa_festejo,
    ranking_produtos_vendas,
    relatorio_final,
    resumo_vendedores_rifa,
    totais_rifa,
)

SECOES_DISPONIVEIS = {
    "resumo": "Resumo consolidado",
    "caixa": "Caixa",
    "leilao": "Leilão",
    "rifa": "Rifa",
    "lancamentos": "Receitas e despesas manuais",
    "notas": "Notas fiscais",
    "produtos": "Ranking de produtos",
}

TODAS_SECOES = list(SECOES_DISPONIVEIS.keys())


def _fmt_data(valor) -> str:
    if not valor:
        return ""
    return valor.strftime("%d/%m/%Y")


def _fmt_data_hora(valor) -> str:
    if not valor:
        return ""
    return valor.strftime("%d/%m/%Y %H:%M")


def _fmt_num(valor: float | int | None) -> str:
    if valor is None:
        return ""
    return f"{float(valor):.2f}".replace(".", ",")


def _escrever_linhas(writer: csv.writer, linhas: list[list]) -> None:
    for linha in linhas:
        writer.writerow(linha)


def _secao(linhas: list[list], titulo: str) -> None:
    linhas.append([])
    linhas.append([f"=== {titulo} ==="])


def _normalizar_secoes(secoes: list[str]) -> list[str]:
    if not secoes or "tudo" in secoes:
        return TODAS_SECOES.copy()
    return [s for s in secoes if s in SECOES_DISPONIVEIS]


def nome_arquivo_csv(festejo_nome: str, ano: int) -> str:
    ascii_nome = unicodedata.normalize("NFKD", festejo_nome).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", ascii_nome)
    slug = re.sub(r"[-\s]+", "-", slug.strip()).strip("-").lower() or "festejo"
    return f"relatorio-{slug}-{ano}.csv"


def gerar_csv_relatorio(db: Session, festejo_id: int, secoes: list[str]) -> tuple[str, str]:
    secoes_ativas = _normalizar_secoes(secoes)
    relatorio = relatorio_final(db, festejo_id)
    festejo = relatorio["festejo"]
    linhas: list[list] = []

    linhas.append(["Relatório financeiro do festejo"])
    linhas.append(["Festejo", festejo.nome])
    linhas.append(["Ano", str(festejo.ano)])
    if festejo.data_inicio:
        linhas.append(["Período início", _fmt_data(festejo.data_inicio)])
    if festejo.data_fim:
        linhas.append(["Período fim", _fmt_data(festejo.data_fim)])
    linhas.append(["Exportado em", _fmt_data_hora(datetime.now())])
    linhas.append(["Seções incluídas", "; ".join(SECOES_DISPONIVEIS[s] for s in secoes_ativas)])

    if "resumo" in secoes_ativas:
        _secao(linhas, SECOES_DISPONIVEIS["resumo"])
        linhas.append(["Indicador", "Valor (R$)"])
        linhas.append(["Receita — Caixa (sem leilão)", _fmt_num(relatorio["receita_caixa"])])
        linhas.append(["Receita — Rifa líquida", _fmt_num(relatorio["receita_rifa"])])
        linhas.append(["Receita — Leilão líquido", _fmt_num(relatorio["receita_leilao"])])
        linhas.append(["Receita — Outras (manuais)", _fmt_num(relatorio["receita_outras"])])
        linhas.append(["Total receitas", _fmt_num(relatorio["total_receitas"])])
        linhas.append(["Total despesas", _fmt_num(relatorio["total_despesas"])])
        linhas.append(["Ganho líquido", _fmt_num(relatorio["ganho_liquido"])])
        linhas.append(["15% Cúria", _fmt_num(relatorio["curia_15"])])
        linhas.append(["Lucro líquido", _fmt_num(relatorio["lucro_liquido"])])

        rifa_totais = relatorio["rifa"]
        linhas.append([])
        linhas.append(["Rifa — indicadores", "Valor"])
        linhas.append(["Doações (A)", _fmt_num(rifa_totais["doacoes"])])
        linhas.append(["Despesas rifa (B)", _fmt_num(rifa_totais["despesas"])])
        linhas.append(["Arrecadado (C)", _fmt_num(rifa_totais["arrecadado"])])
        linhas.append(["Saldo líquido rifa", _fmt_num(rifa_totais["liquido"])])

        leilao_totais = relatorio["leilao"]
        linhas.append([])
        linhas.append(["Leilão — indicadores", "Valor (R$)"])
        linhas.append(["Entradas", _fmt_num(leilao_totais["entradas"])])
        linhas.append(["Saídas", _fmt_num(leilao_totais["saidas"])])
        linhas.append(["Líquido", _fmt_num(leilao_totais["liquido"])])

    if "caixa" in secoes_ativas:
        _secao(linhas, SECOES_DISPONIVEIS["caixa"])
        resumo_caixa = listar_caixa_festejo(db, festejo_id)
        totais = resumo_caixa["totais"]

        linhas.append(["Totais consolidados — formas de pagamento"])
        linhas.append(["Indicador", "Valor (R$)"])
        linhas.append(["Dinheiro (líquido)", _fmt_num(totais["dinheiro"])])
        linhas.append(["Débito", _fmt_num(totais["debito"])])
        linhas.append(["Crédito", _fmt_num(totais["credito"])])
        linhas.append(["Pix", _fmt_num(totais["pix"])])
        linhas.append(["Troco", _fmt_num(totais["troco"])])
        linhas.append(["Sangrias", _fmt_num(totais["sangrias"])])
        linhas.append(["Total caixa (sem leilão)", _fmt_num(totais["total_caixa_sem_leilao"])])
        linhas.append(["Total vendas PDF", _fmt_num(totais["total_vendas_pdf"])])
        linhas.append(["Dias lançados", str(totais["dias_count"])])

        linhas.append([])
        linhas.append(["Caixa por dia"])
        linhas.append([
            "Data",
            "Dia",
            "Rótulo",
            "Dinheiro",
            "Débito",
            "Crédito",
            "Pix",
            "Troco",
            "Leilão pago no caixa",
            "Total caixa (s/ leilão)",
            "PDF — total vendas",
            "PDF — dinheiro",
            "PDF — débito",
            "PDF — crédito",
            "PDF — pix",
        ])
        for item in resumo_caixa["dias"]:
            dia = item["dia"]
            cons = item["consolidacao"]
            pdf = dia.relatorio_pdf
            linhas.append([
                _fmt_data(dia.data),
                str(dia.numero_dia or ""),
                dia.rotulo or "",
                _fmt_num(cons["dinheiro"]),
                _fmt_num(cons["debito"]),
                _fmt_num(cons["credito"]),
                _fmt_num(cons["pix"]),
                _fmt_num(cons["total_troco"]),
                _fmt_num(cons["total_leilao_pago_caixa"]),
                _fmt_num(cons["total_caixa_sem_leilao"]),
                _fmt_num(pdf.total_vendas if pdf else 0),
                _fmt_num(pdf.dinheiro if pdf else 0),
                _fmt_num(pdf.debito if pdf else 0),
                _fmt_num(pdf.credito if pdf else 0),
                _fmt_num(pdf.pix if pdf else 0),
            ])

        sangrias = (
            db.query(Sangria)
            .join(DiaFestejo, Sangria.dia_id == DiaFestejo.id)
            .options(joinedload(Sangria.dia))
            .filter(DiaFestejo.festejo_id == festejo_id)
            .order_by(DiaFestejo.data, Sangria.id)
            .all()
        )
        if sangrias:
            linhas.append([])
            linhas.append(["Sangrias"])
            linhas.append(["Data do dia", "Destino", "Valor (R$)"])
            for sangria in sangrias:
                linhas.append([
                    _fmt_data(sangria.dia.data) if sangria.dia else "",
                    sangria.destino,
                    _fmt_num(sangria.valor),
                ])

    if "leilao" in secoes_ativas:
        _secao(linhas, SECOES_DISPONIVEIS["leilao"])
        leilao_totais = relatorio["leilao"]
        linhas.append(["Totais do leilão"])
        linhas.append(["Entradas (R$)", _fmt_num(leilao_totais["entradas"])])
        linhas.append(["Saídas (R$)", _fmt_num(leilao_totais["saidas"])])
        linhas.append(["Líquido (R$)", _fmt_num(leilao_totais["liquido"])])

        movimentos = (
            db.query(LeilaoMovimento)
            .join(DiaFestejo, LeilaoMovimento.dia_id == DiaFestejo.id)
            .options(joinedload(LeilaoMovimento.dia))
            .filter(DiaFestejo.festejo_id == festejo_id)
            .order_by(DiaFestejo.data, LeilaoMovimento.id)
            .all()
        )
        linhas.append([])
        linhas.append(["Movimentos do leilão"])
        linhas.append(["Data", "Dia", "Rótulo", "Tipo", "Descrição", "Valor (R$)", "Observação"])
        for mov in movimentos:
            dia = mov.dia
            linhas.append([
                _fmt_data(dia.data) if dia else "",
                str(dia.numero_dia or "") if dia else "",
                (dia.rotulo or "") if dia else "",
                mov.tipo,
                mov.descricao,
                _fmt_num(mov.valor),
                mov.observacao or "",
            ])

    if "rifa" in secoes_ativas:
        _secao(linhas, SECOES_DISPONIVEIS["rifa"])
        rifa_totais = totais_rifa(db, festejo_id)
        linhas.append(["Totais da rifa"])
        linhas.append(["Indicador", "Valor"])
        linhas.append(["Doações (A)", _fmt_num(rifa_totais["doacoes"])])
        linhas.append(["Despesas (B)", _fmt_num(rifa_totais["despesas"])])
        linhas.append(["Arrecadado (C)", _fmt_num(rifa_totais["arrecadado"])])
        linhas.append(["Premiações", _fmt_num(rifa_totais["premiacoes"])])
        linhas.append(["Saldo líquido", _fmt_num(rifa_totais["liquido"])])
        linhas.append(["Valor rifas (C/2)", _fmt_num(rifa_totais["valor_rifas"])])
        linhas.append(["Blocos vendidos", _fmt_num(rifa_totais["qtd_blocos"])])

        movimentos = (
            db.query(RifaMovimento)
            .filter(RifaMovimento.festejo_id == festejo_id)
            .order_by(RifaMovimento.data, RifaMovimento.id)
            .all()
        )
        linhas.append([])
        linhas.append(["Movimentos da rifa"])
        linhas.append(["Data", "Tipo", "Categoria", "Vendedor", "Descrição", "Valor (R$)"])
        for mov in movimentos:
            linhas.append([
                _fmt_data(mov.data),
                mov.tipo,
                mov.categoria,
                mov.vendedor or "",
                mov.descricao,
                _fmt_num(mov.valor),
            ])

        vendedores = resumo_vendedores_rifa(db, festejo_id)
        if vendedores:
            linhas.append([])
            linhas.append(["Ranking de vendedores"])
            linhas.append(["Vendedor", "Rifas (R$)", "Blocos", "Premiação (R$)"])
            for v in vendedores:
                linhas.append([
                    v["nome"],
                    _fmt_num(v["rifas"]),
                    _fmt_num(v["blocos"]),
                    _fmt_num(v["premiacao"]),
                ])

    if "lancamentos" in secoes_ativas:
        _secao(linhas, SECOES_DISPONIVEIS["lancamentos"])

        linhas.append(["Receitas manuais"])
        linhas.append(["Categoria", "Descrição", "Valor (R$)"])
        if relatorio["receitas_manuais"]:
            for r in relatorio["receitas_manuais"]:
                linhas.append([r.categoria, r.descricao, _fmt_num(r.valor)])
        else:
            linhas.append(["—", "Nenhuma receita manual", "0,00"])

        linhas.append([])
        linhas.append(["Despesas"])
        linhas.append(["Categoria", "Descrição", "Valor (R$)", "Origem"])
        if relatorio["despesas"]:
            for d in relatorio["despesas"]:
                origem = "Nota fiscal" if d.nota_fiscal else "Manual"
                linhas.append([d.categoria, d.descricao, _fmt_num(d.valor), origem])
        else:
            linhas.append(["—", "Nenhuma despesa", "0,00", "—"])

    if "notas" in secoes_ativas:
        _secao(linhas, SECOES_DISPONIVEIS["notas"])
        notas = (
            db.query(NotaFiscal)
            .filter(NotaFiscal.festejo_id == festejo_id)
            .order_by(NotaFiscal.data_emissao, NotaFiscal.id)
            .all()
        )
        linhas.append([
            "Número",
            "Série",
            "Emitente",
            "CNPJ",
            "Data emissão",
            "Categoria",
            "Natureza",
            "Valor (R$)",
            "CFOP",
            "Itens / resumo",
            "Chave",
            "Tipo",
        ])
        for nota in notas:
            linhas.append([
                nota.numero,
                nota.serie,
                nota.emitente_nome,
                nota.emitente_cnpj,
                _fmt_data(nota.data_emissao),
                nota.categoria,
                nota.natureza_operacao,
                _fmt_num(nota.valor_total),
                nota.cfop_principal,
                nota.produtos_resumo,
                nota.chave,
                "Manual" if is_nota_manual(nota.chave) else "Importada",
            ])

    if "produtos" in secoes_ativas:
        _secao(linhas, SECOES_DISPONIVEIS["produtos"])
        ranking = ranking_produtos_vendas(db, festejo_id)
        linhas.append(["Posição", "Produto", "Código", "Quantidade", "Total vendido (R$)"])
        if ranking:
            for item in ranking:
                linhas.append([
                    str(item["posicao"]),
                    item["produto"],
                    str(item["codigo"] or ""),
                    _fmt_num(item["quantidade"]),
                    _fmt_num(item["total"]),
                ])
        else:
            linhas.append(["—", "Nenhum produto (importe PDFs no caixa)", "", "0,00", "0,00"])

    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    _escrever_linhas(writer, linhas)

    return buffer.getvalue(), nome_arquivo_csv(festejo.nome, festejo.ano)
