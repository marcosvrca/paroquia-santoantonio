from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.models import (
    CaixaRegistro,
    DiaFestejo,
    Festejo,
    Investimento,
    LancamentoFinanceiro,
    LeilaoMovimento,
    NotaFiscal,
    ProdutoVenda,
    RelatorioPdf,
    PatrocinioMovimento,
    RifaMovimento,
    Sangria,
)
from app.nfe_parser import NFeParsed, classificar_categoria, validar_chave
from app.rifa_xlsx_parser import PRECO_BLOCO, RifaPlanilha, blocos_de_rifas, parse_rifa_xlsx

RIFA_CATEGORIAS = ("doacao", "despesa", "venda", "premiacao", "outro")


def calc_caixa(caixa: CaixaRegistro) -> dict:
    total_recebimentos = caixa.dinheiro + caixa.debito + caixa.credito + caixa.pix
    total_caixa_sem_leilao = total_recebimentos - caixa.troco - caixa.leilao_pago_caixa

    return {
        "dinheiro": caixa.dinheiro,
        "debito": caixa.debito,
        "credito": caixa.credito,
        "pix": caixa.pix,
        "troco": caixa.troco,
        "leilao_pago_caixa": caixa.leilao_pago_caixa,
        "total_recebimentos": round(total_recebimentos, 2),
        "total_caixa_sem_leilao": round(total_caixa_sem_leilao, 2),
        "dinheiro_liquido": round(caixa.dinheiro - caixa.troco, 2),
    }


def caixa_tem_recebimentos(caixa: CaixaRegistro | None) -> bool:
    if not caixa:
        return False
    return bool(
        caixa.dinheiro or caixa.debito or caixa.credito or caixa.pix or caixa.troco or caixa.leilao_pago_caixa
    )


def sincronizar_pdf_para_caixa(dia: DiaFestejo, pdf: RelatorioPdf, sobrescrever: bool = False) -> bool:
    if not pdf or pdf.eh_acumulado or not dia.caixa:
        return False

    if caixa_tem_recebimentos(dia.caixa) and not sobrescrever:
        return False

    caixa = dia.caixa
    caixa.dinheiro = pdf.dinheiro
    caixa.debito = pdf.debito
    caixa.credito = pdf.credito
    caixa.pix = pdf.pix
    return True


def calc_consolidacao_dia(dia: DiaFestejo) -> dict:
    caixa_calc = calc_caixa(dia.caixa) if dia.caixa else {
        "dinheiro": 0,
        "debito": 0,
        "credito": 0,
        "pix": 0,
        "troco": 0,
        "leilao_pago_caixa": 0,
        "total_recebimentos": 0,
        "total_caixa_sem_leilao": 0,
        "dinheiro_liquido": 0,
    }

    leilao_entradas = sum(m.valor for m in dia.leilao_movimentos if m.tipo == "entrada")
    leilao_saidas = sum(m.valor for m in dia.leilao_movimentos if m.tipo == "saida")
    saldo_leilao = leilao_entradas - leilao_saidas

    pdf = dia.relatorio_pdf
    pdf_dinheiro = pdf.dinheiro if pdf else 0
    pdf_debito = pdf.debito if pdf else 0
    pdf_credito = pdf.credito if pdf else 0
    pdf_pix = pdf.pix if pdf else 0
    pdf_total_pagamentos = round(pdf_dinheiro + pdf_debito + pdf_credito + pdf_pix, 2) if pdf else 0
    pdf_total_vendas = pdf.total_vendas if pdf else 0
    gratuidade_total = round(pdf.total_gratuidade, 2) if pdf else 0.0
    gratuidade_produtos = (
        [p for p in pdf.produtos if p.secao == "gratuidade"] if pdf else []
    )
    sangrias_total = round(sum(s.valor for s in dia.sangrias), 2)
    saidas_total = round(sangrias_total + gratuidade_total, 2)

    diff_pagamentos = None
    diff_dinheiro = None
    diff_debito = None
    diff_credito = None
    diff_pix = None
    diff_vendas = None

    if pdf and not pdf.eh_acumulado:
        diff_dinheiro = round(caixa_calc["dinheiro_liquido"] - pdf_dinheiro, 2)
        diff_debito = round(caixa_calc["debito"] - pdf_debito, 2)
        diff_credito = round(caixa_calc["credito"] - pdf_credito, 2)
        diff_pix = round(caixa_calc["pix"] - pdf_pix, 2)
        diff_pagamentos = round(caixa_calc["total_caixa_sem_leilao"] - pdf_total_pagamentos, 2)
        diff_vendas = round(caixa_calc["total_recebimentos"] - pdf_total_vendas, 2)

    return {
        "caixa": caixa_calc,
        "dinheiro": caixa_calc["dinheiro_liquido"],
        "debito": caixa_calc["debito"],
        "credito": caixa_calc["credito"],
        "pix": caixa_calc["pix"],
        "total_recebimentos_bruto": caixa_calc["total_recebimentos"],
        "total_troco": caixa_calc["troco"],
        "total_leilao_pago_caixa": caixa_calc["leilao_pago_caixa"],
        "total_caixa_sem_leilao": caixa_calc["total_caixa_sem_leilao"],
        "pdf_dinheiro": pdf_dinheiro,
        "pdf_debito": pdf_debito,
        "pdf_credito": pdf_credito,
        "pdf_pix": pdf_pix,
        "pdf_total_pagamentos": pdf_total_pagamentos,
        "pdf_total_vendas": pdf_total_vendas,
        "pdf_total_geral": pdf.total_geral if pdf else 0,
        "pdf_eh_acumulado": pdf.eh_acumulado if pdf else False,
        "diferenca_pagamentos": diff_pagamentos,
        "diferenca_dinheiro": diff_dinheiro,
        "diferenca_debito": diff_debito,
        "diferenca_credito": diff_credito,
        "diferenca_pix": diff_pix,
        "diferenca_vendas": diff_vendas,
        "leilao_entradas": round(leilao_entradas, 2),
        "leilao_saidas": round(leilao_saidas, 2),
        "saldo_leilao_dia": round(saldo_leilao, 2),
        "sangrias_total": sangrias_total,
        "gratuidade_total": gratuidade_total,
        "gratuidade_produtos": gratuidade_produtos,
        "saidas_total": saidas_total,
    }


def migrar_para_caixa_unico(db: Session) -> None:
    """Consolida registros antigos (5 caixas/dia) em um único caixa."""
    dias = db.query(DiaFestejo.id).all()
    for (dia_id,) in dias:
        rows = db.execute(
            text("SELECT id, dinheiro, debito, credito, pix, troco, leilao_pago_caixa FROM caixas_registro WHERE dia_id = :dia_id ORDER BY id"),
            {"dia_id": dia_id},
        ).fetchall()

        if len(rows) <= 1:
            continue

        principal_id = rows[0][0]
        totals = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        for row in rows:
            for i, val in enumerate(row[1:], start=0):
                totals[i] += float(val or 0)

        db.execute(
            text(
                """
                UPDATE caixas_registro
                SET dinheiro = :d, debito = :db, credito = :cr, pix = :px,
                    troco = :t, leilao_pago_caixa = :l, caixa_numero = 1
                WHERE id = :id
                """
            ),
            {
                "id": principal_id,
                "d": totals[0],
                "db": totals[1],
                "cr": totals[2],
                "px": totals[3],
                "t": totals[4],
                "l": totals[5],
            },
        )
        db.execute(
            text("DELETE FROM caixas_registro WHERE dia_id = :dia_id AND id != :id"),
            {"dia_id": dia_id, "id": principal_id},
        )

    db.commit()


def ensure_caixa_dia(db: Session, dia: DiaFestejo) -> CaixaRegistro:
    if dia.caixa:
        return dia.caixa

    existente = db.query(CaixaRegistro).filter(CaixaRegistro.dia_id == dia.id).first()
    if existente:
        return existente

    caixa = CaixaRegistro(dia_id=dia.id, caixa_numero=1)
    db.add(caixa)
    db.commit()
    db.refresh(caixa)
    return caixa


def get_or_create_festejo_ativo(db: Session) -> Festejo:
    festejo = db.query(Festejo).filter(Festejo.ativo.is_(True)).first()
    if not festejo:
        festejo = Festejo(nome="Festejo de Santo Antônio", ano=date.today().year, ativo=True)
        db.add(festejo)
        db.commit()
        db.refresh(festejo)
    return festejo


def get_dia_completo(db: Session, dia_id: int) -> DiaFestejo | None:
    return (
        db.query(DiaFestejo)
        .options(
            joinedload(DiaFestejo.caixa),
            joinedload(DiaFestejo.relatorio_pdf).joinedload(RelatorioPdf.produtos),
            joinedload(DiaFestejo.leilao_movimentos),
            joinedload(DiaFestejo.rifa_movimentos),
            joinedload(DiaFestejo.sangrias),
        )
        .filter(DiaFestejo.id == dia_id)
        .first()
    )


def migrar_rifa_campos(db: Session) -> None:
    cols = db.execute(text("PRAGMA table_info(rifa_movimentos)")).fetchall()
    names = {c[1] for c in cols}
    if "categoria" not in names:
        db.execute(text("ALTER TABLE rifa_movimentos ADD COLUMN categoria VARCHAR(30) DEFAULT 'outro'"))
    if "vendedor" not in names:
        db.execute(text("ALTER TABLE rifa_movimentos ADD COLUMN vendedor VARCHAR(120)"))
    db.commit()


def totais_rifa(db: Session, festejo_id: int) -> dict:
    movimentos = db.query(RifaMovimento).filter(RifaMovimento.festejo_id == festejo_id).all()
    doacoes = sum(m.valor for m in movimentos if m.categoria == "doacao")
    despesas = sum(m.valor for m in movimentos if m.categoria == "despesa")
    vendas = sum(m.valor for m in movimentos if m.categoria == "venda")
    premiacoes = sum(m.valor for m in movimentos if m.categoria == "premiacao")
    entradas = sum(m.valor for m in movimentos if m.tipo == "entrada")
    saidas = sum(m.valor for m in movimentos if m.tipo == "saida")
    total_a = round(doacoes, 2)
    total_b = round(despesas, 2)
    total_c = round(vendas, 2)
    saldo_final = round((total_a + total_c) - total_b, 2)
    valor_rifas = round(total_c / 2, 2)
    qtd_blocos = round(valor_rifas / PRECO_BLOCO, 2) if PRECO_BLOCO else 0
    return {
        "doacoes": total_a,
        "despesas": total_b,
        "arrecadado": total_c,
        "premiacoes": round(premiacoes, 2),
        "saldo_final": saldo_final,
        "valor_rifas": valor_rifas,
        "qtd_blocos": qtd_blocos,
        "preco_bloco": PRECO_BLOCO,
        "entradas": round(entradas, 2),
        "saidas": round(saidas, 2),
        "liquido": saldo_final,
    }


def resumo_vendedores_rifa(db: Session, festejo_id: int) -> list[dict]:
    movimentos = (
        db.query(RifaMovimento)
        .filter(
            RifaMovimento.festejo_id == festejo_id,
            RifaMovimento.categoria.in_(("venda", "premiacao")),
        )
        .all()
    )
    por_nome: dict[str, dict] = {}
    for mov in movimentos:
        nome = (mov.vendedor or mov.descricao or "Sem nome").strip()
        if nome not in por_nome:
            por_nome[nome] = {"nome": nome, "rifas": 0.0, "blocos": 0.0, "premiacao": 0.0}
        if mov.categoria == "venda":
            por_nome[nome]["rifas"] += mov.valor
        elif mov.categoria == "premiacao":
            por_nome[nome]["premiacao"] += mov.valor

    lista = []
    for item in por_nome.values():
        item["rifas"] = round(item["rifas"], 2)
        item["blocos"] = blocos_de_rifas(item["rifas"])
        item["premiacao"] = round(item["premiacao"], 2)
        lista.append(item)
    return sorted(lista, key=lambda x: x["rifas"], reverse=True)


def importar_planilha_rifa(
    db: Session,
    festejo_id: int,
    planilha: RifaPlanilha,
    substituir: bool = True,
) -> dict:
    if substituir:
        db.query(RifaMovimento).filter(RifaMovimento.festejo_id == festejo_id).delete()
        db.flush()

    criados = {"doacoes": 0, "despesas": 0, "vendas": 0, "premiacoes": 0}

    for descricao, valor in planilha.doacoes:
        db.add(
            RifaMovimento(
                festejo_id=festejo_id,
                tipo="entrada",
                categoria="doacao",
                descricao=descricao,
                valor=valor,
                data=date.today(),
            )
        )
        criados["doacoes"] += 1

    for descricao, valor in planilha.despesas:
        db.add(
            RifaMovimento(
                festejo_id=festejo_id,
                tipo="saida",
                categoria="despesa",
                descricao=descricao,
                valor=valor,
                data=date.today(),
            )
        )
        criados["despesas"] += 1

    for vendedor in planilha.vendedores:
        db.add(
            RifaMovimento(
                festejo_id=festejo_id,
                tipo="entrada",
                categoria="venda",
                vendedor=vendedor.nome,
                descricao=f"Vendas — {vendedor.nome}",
                valor=vendedor.valor_rifas,
                data=date.today(),
            )
        )
        criados["vendas"] += 1
        if vendedor.premiacao is not None and vendedor.premiacao > 0:
            db.add(
                RifaMovimento(
                    festejo_id=festejo_id,
                    tipo="saida",
                    categoria="premiacao",
                    vendedor=vendedor.nome,
                    descricao=f"Premiação — {vendedor.nome}",
                    valor=vendedor.premiacao,
                    data=date.today(),
                )
            )
            criados["premiacoes"] += 1

    total_vendedores = round(sum(v.valor_rifas for v in planilha.vendedores), 2)
    if planilha.arrecadado_total and planilha.arrecadado_total > total_vendedores + 0.01:
        diff = round(planilha.arrecadado_total - total_vendedores, 2)
        db.add(
            RifaMovimento(
                festejo_id=festejo_id,
                tipo="entrada",
                categoria="venda",
                vendedor="Outros",
                descricao="Arrecadado (C) não detalhado no INCENTIVO",
                valor=diff,
                data=date.today(),
            )
        )
        criados["vendas"] += 1

    db.commit()
    return criados


def totais_patrocinios(db: Session, festejo_id: int) -> dict:
    movimentos = (
        db.query(PatrocinioMovimento)
        .filter(PatrocinioMovimento.festejo_id == festejo_id)
        .all()
    )
    entradas = sum(m.valor for m in movimentos if m.tipo == "entrada")
    saidas = sum(m.valor for m in movimentos if m.tipo == "saida")
    return {
        "entradas": round(entradas, 2),
        "saidas": round(saidas, 2),
        "liquido": round(entradas - saidas, 2),
        "quantidade": len(movimentos),
    }


def resumo_patrocinadores(db: Session, festejo_id: int) -> list[dict]:
    movimentos = (
        db.query(PatrocinioMovimento)
        .filter(
            PatrocinioMovimento.festejo_id == festejo_id,
            PatrocinioMovimento.tipo == "entrada",
        )
        .all()
    )
    por_nome: dict[str, float] = {}
    for mov in movimentos:
        nome = (mov.patrocinador or mov.descricao or "Sem nome").strip()
        por_nome[nome] = por_nome.get(nome, 0.0) + mov.valor
    return sorted(
        [{"nome": nome, "total": round(total, 2)} for nome, total in por_nome.items()],
        key=lambda x: x["total"],
        reverse=True,
    )


def sugerir_investido_em(nota: NotaFiscal) -> str:
    if nota.natureza_operacao.strip():
        return nota.natureza_operacao.strip()[:255]
    if nota.produtos_resumo.strip():
        return nota.produtos_resumo.strip()[:255]
    if nota.categoria.strip():
        return nota.categoria.strip()[:255]
    return (nota.emitente_nome or "Investimento").strip()[:255]


def totais_investimentos(db: Session, festejo_id: int) -> dict:
    itens = db.query(Investimento).filter(Investimento.festejo_id == festejo_id).all()
    total = sum(i.valor for i in itens)
    vinculados = sum(1 for i in itens if i.nota_id)
    return {
        "total": round(total, 2),
        "quantidade": len(itens),
        "vinculados_despesas": vinculados,
        "avulsos": len(itens) - vinculados,
    }


def mapa_investimentos_por_nota(db: Session, festejo_id: int) -> dict[int, Investimento]:
    itens = (
        db.query(Investimento)
        .filter(Investimento.festejo_id == festejo_id, Investimento.nota_id.isnot(None))
        .all()
    )
    return {item.nota_id: item for item in itens if item.nota_id}


def resumo_investimentos_por_item(db: Session, festejo_id: int) -> list[dict]:
    itens = db.query(Investimento).filter(Investimento.festejo_id == festejo_id).all()
    por_item: dict[str, dict] = {}
    for item in itens:
        nome = item.investido_em.strip() or "Sem descrição"
        if nome not in por_item:
            por_item[nome] = {"item": nome, "total": 0.0, "quantidade": 0}
        por_item[nome]["total"] += item.valor
        por_item[nome]["quantidade"] += 1
    return sorted(
        [
            {
                "item": v["item"],
                "total": round(v["total"], 2),
                "quantidade": v["quantidade"],
            }
            for v in por_item.values()
        ],
        key=lambda x: x["total"],
        reverse=True,
    )


def criar_investimento(
    db: Session,
    festejo_id: int,
    *,
    investido_em: str,
    valor: float,
    data_inv: date | None = None,
    observacao: str = "",
    nota_id: int | None = None,
) -> Investimento:
    texto = investido_em.strip()
    if not texto:
        raise ValueError("Informe em que foi investido.")
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")

    if nota_id:
        nota = db.get(NotaFiscal, nota_id)
        if not nota or nota.festejo_id != festejo_id:
            raise ValueError("Despesa não encontrada.")
        existente = (
            db.query(Investimento)
            .filter(Investimento.nota_id == nota_id)
            .first()
        )
        if existente:
            raise ValueError("Esta despesa já possui um investimento cadastrado.")

    item = Investimento(
        festejo_id=festejo_id,
        nota_id=nota_id,
        valor=round(valor, 2),
        investido_em=texto,
        data=data_inv,
        observacao=observacao.strip() or None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def atualizar_investimento(
    db: Session,
    inv_id: int,
    festejo_id: int,
    *,
    investido_em: str,
    valor: float,
    data_inv: date | None = None,
    observacao: str = "",
) -> Investimento:
    item = db.get(Investimento, inv_id)
    if not item or item.festejo_id != festejo_id:
        raise ValueError("Investimento não encontrado.")
    texto = investido_em.strip()
    if not texto:
        raise ValueError("Informe em que foi investido.")
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")

    item.investido_em = texto
    item.valor = round(valor, 2)
    item.data = data_inv
    item.observacao = observacao.strip() or None
    db.commit()
    db.refresh(item)
    return item


def excluir_investimento(db: Session, inv_id: int, festejo_id: int) -> None:
    item = db.get(Investimento, inv_id)
    if not item or item.festejo_id != festejo_id:
        raise ValueError("Investimento não encontrado.")
    db.delete(item)
    db.commit()


def totais_leilao(db: Session, festejo_id: int) -> dict:
    dias = db.query(DiaFestejo).filter(DiaFestejo.festejo_id == festejo_id).all()
    dia_ids = [d.id for d in dias]
    movimentos = db.query(LeilaoMovimento).filter(LeilaoMovimento.dia_id.in_(dia_ids)).all()
    entradas = sum(m.valor for m in movimentos if m.tipo == "entrada")
    saidas = sum(m.valor for m in movimentos if m.tipo == "saida")
    return {
        "entradas": round(entradas, 2),
        "saidas": round(saidas, 2),
        "liquido": round(entradas - saidas, 2),
    }


def totais_caixa_festejo(db: Session, festejo_id: int) -> dict:
    resumo = listar_caixa_festejo(db, festejo_id)
    return resumo["totais"]


def listar_caixa_festejo(db: Session, festejo_id: int) -> dict:
    dias = (
        db.query(DiaFestejo)
        .filter(DiaFestejo.festejo_id == festejo_id)
        .order_by(DiaFestejo.data)
        .all()
    )
    items: list[dict] = []
    totais = {
        "total_caixa_sem_leilao": 0.0,
        "total_vendas_pdf": 0.0,
        "dinheiro": 0.0,
        "debito": 0.0,
        "credito": 0.0,
        "pix": 0.0,
        "troco": 0.0,
        "sangrias": 0.0,
        "gratuidade": 0.0,
        "saidas_total": 0.0,
        "dias_count": len(dias),
    }

    for dia in dias:
        dia_full = get_dia_completo(db, dia.id)
        if not dia_full:
            continue
        if not dia_full.caixa:
            ensure_caixa_dia(db, dia_full)
            dia_full = get_dia_completo(db, dia.id)
        cons = calc_consolidacao_dia(dia_full)
        items.append({"dia": dia_full, "consolidacao": cons})
        totais["total_caixa_sem_leilao"] += cons["total_caixa_sem_leilao"]
        totais["dinheiro"] += cons["dinheiro"]
        totais["debito"] += cons["debito"]
        totais["credito"] += cons["credito"]
        totais["pix"] += cons["pix"]
        totais["troco"] += cons["total_troco"]
        totais["sangrias"] += cons["sangrias_total"]
        totais["gratuidade"] += cons["gratuidade_total"]
        totais["saidas_total"] += cons["saidas_total"]
        if dia_full.relatorio_pdf:
            totais["total_vendas_pdf"] += dia_full.relatorio_pdf.total_vendas

    for key in totais:
        if key != "dias_count":
            totais[key] = round(totais[key], 2)

    return {"dias": items, "totais": totais}


def resumo_gratuidade_festejo(db: Session, festejo_id: int) -> dict:
    """Agrega gratuidade (saídas de funcionários) dos PDFs do caixa."""
    query = (
        db.query(ProdutoVenda)
        .join(RelatorioPdf)
        .filter(
            RelatorioPdf.festejo_id == festejo_id,
            ProdutoVenda.secao == "gratuidade",
        )
    )
    linhas = query.filter(RelatorioPdf.eh_acumulado.is_(False)).all()
    if not linhas:
        linhas = query.all()

    agregado: dict[tuple[str, int | None], dict] = {}
    for linha in linhas:
        nome = linha.produto.strip()
        chave = (nome.lower(), linha.codigo)
        if chave not in agregado:
            agregado[chave] = {
                "produto": nome,
                "codigo": linha.codigo,
                "quantidade": 0.0,
                "total": 0.0,
            }
        agregado[chave]["quantidade"] += linha.quantidade
        agregado[chave]["total"] += linha.total

    produtos = sorted(
        agregado.values(),
        key=lambda x: (-x["quantidade"], -x["total"], x["produto"].lower()),
    )
    for pos, item in enumerate(produtos, start=1):
        item["posicao"] = pos
        item["quantidade"] = round(item["quantidade"], 2)
        item["total"] = round(item["total"], 2)

    pdfs = (
        db.query(RelatorioPdf)
        .filter(RelatorioPdf.festejo_id == festejo_id, RelatorioPdf.eh_acumulado.is_(False))
        .all()
    )
    if not pdfs:
        pdfs = db.query(RelatorioPdf).filter(RelatorioPdf.festejo_id == festejo_id).all()
    total = round(sum(p.total_gratuidade for p in pdfs), 2)

    return {"produtos": produtos, "total": total}


def ranking_produtos_vendas(db: Session, festejo_id: int) -> list[dict]:
    """Consolida produtos vendidos (PDFs do caixa) e ordena por quantidade."""
    query = (
        db.query(ProdutoVenda)
        .join(RelatorioPdf)
        .filter(
            RelatorioPdf.festejo_id == festejo_id,
            ProdutoVenda.secao == "vendas",
        )
    )
    linhas = query.filter(RelatorioPdf.eh_acumulado.is_(False)).all()
    if not linhas:
        linhas = query.all()

    agregado: dict[tuple[str, int | None], dict] = {}
    for linha in linhas:
        nome = linha.produto.strip()
        chave = (nome.lower(), linha.codigo)
        if chave not in agregado:
            agregado[chave] = {
                "produto": nome,
                "codigo": linha.codigo,
                "quantidade": 0.0,
                "total": 0.0,
            }
        agregado[chave]["quantidade"] += linha.quantidade
        agregado[chave]["total"] += linha.total

    ranking = sorted(
        agregado.values(),
        key=lambda item: (-item["quantidade"], -item["total"], item["produto"].lower()),
    )
    for pos, item in enumerate(ranking, start=1):
        item["posicao"] = pos
        item["quantidade"] = round(item["quantidade"], 2)
        item["total"] = round(item["total"], 2)

    return ranking


def relatorio_final(db: Session, festejo_id: int) -> dict:
    festejo = db.get(Festejo, festejo_id)
    caixa = totais_caixa_festejo(db, festejo_id)
    rifa = totais_rifa(db, festejo_id)
    patrocinios = totais_patrocinios(db, festejo_id)
    leilao = totais_leilao(db, festejo_id)

    lancamentos = (
        db.query(LancamentoFinanceiro)
        .options(joinedload(LancamentoFinanceiro.nota_fiscal))
        .filter(LancamentoFinanceiro.festejo_id == festejo_id)
        .order_by(LancamentoFinanceiro.tipo, LancamentoFinanceiro.categoria)
        .all()
    )

    receitas_manuais = [l for l in lancamentos if l.tipo == "receita"]
    despesas = [l for l in lancamentos if l.tipo == "despesa"]

    receita_caixa = caixa["total_caixa_sem_leilao"]
    receita_rifa = rifa["liquido"]
    receita_patrocinios = patrocinios["liquido"]
    receita_leilao = leilao["liquido"]
    receita_outras = sum(l.valor for l in receitas_manuais)

    total_receitas = receita_caixa + receita_rifa + receita_patrocinios + receita_leilao + receita_outras
    total_despesas = sum(d.valor for d in despesas)
    ganho_liquido = total_receitas - total_despesas
    curia_15 = ganho_liquido * 0.15
    lucro_liquido = ganho_liquido - curia_15

    return {
        "festejo": festejo,
        "caixa": caixa,
        "rifa": rifa,
        "patrocinios": patrocinios,
        "leilao": leilao,
        "receitas_manuais": receitas_manuais,
        "despesas": despesas,
        "receita_caixa": round(receita_caixa, 2),
        "receita_rifa": round(receita_rifa, 2),
        "receita_patrocinios": round(receita_patrocinios, 2),
        "receita_leilao": round(receita_leilao, 2),
        "receita_outras": round(receita_outras, 2),
        "total_receitas": round(total_receitas, 2),
        "total_despesas": round(total_despesas, 2),
        "ganho_liquido": round(ganho_liquido, 2),
        "curia_15": round(curia_15, 2),
        "lucro_liquido": round(lucro_liquido, 2),
    }


def dados_infografico(db: Session, festejo_id: int) -> dict:
    relatorio = relatorio_final(db, festejo_id)
    festejo = relatorio["festejo"]

    dias = (
        db.query(DiaFestejo)
        .options(joinedload(DiaFestejo.caixa))
        .options(joinedload(DiaFestejo.relatorio_pdf))
        .filter(DiaFestejo.festejo_id == festejo_id)
        .order_by(DiaFestejo.data)
        .all()
    )
    dias_resumo = []
    for dia in dias:
        cons = calc_consolidacao_dia(dia)
        dias_resumo.append(
            {
                "rotulo": dia.rotulo or f"Dia {dia.numero_dia or ''}".strip(),
                "data": dia.data,
                "caixa": cons["total_caixa_sem_leilao"],
                "leilao": cons["saldo_leilao_dia"],
            }
        )

    despesas_por_categoria: dict[str, float] = {}
    for d in relatorio["despesas"]:
        cat = d.categoria or "Outras"
        despesas_por_categoria[cat] = despesas_por_categoria.get(cat, 0) + d.valor
    despesas_top = sorted(
        [{"categoria": k, "valor": round(v, 2)} for k, v in despesas_por_categoria.items()],
        key=lambda x: x["valor"],
        reverse=True,
    )[:6]

    notas = totais_notas_fiscais(db, festejo_id)
    vendedores = resumo_vendedores_rifa(db, festejo_id)[:5]
    patrocinadores_top = resumo_patrocinadores(db, festejo_id)[:5]
    investimentos_totais = totais_investimentos(db, festejo_id)
    investimentos_top = resumo_investimentos_por_item(db, festejo_id)[:6]
    ranking_produtos = ranking_produtos_vendas(db, festejo_id)
    caixa_totais = totais_caixa_festejo(db, festejo_id)

    total_receitas = relatorio["total_receitas"]
    margem_lucro = round(
        (relatorio["lucro_liquido"] / total_receitas * 100) if total_receitas else 0, 1
    )

    def pct_receita(valor: float) -> float:
        if not total_receitas:
            return 0.0
        return round((valor / total_receitas) * 100, 1)

    return {
        **relatorio,
        "festejo": festejo,
        "dias": dias_resumo,
        "despesas_top": despesas_top,
        "notas": notas,
        "vendedores_top": vendedores,
        "patrocinadores_top": patrocinadores_top,
        "investimentos_totais": investimentos_totais,
        "investimentos_top": investimentos_top,
        "ranking_produtos": ranking_produtos,
        "caixa_totais": caixa_totais,
        "qtd_dias": len(dias_resumo),
        "margem_lucro": margem_lucro,
        "pct_receita_caixa": pct_receita(relatorio["receita_caixa"]),
        "pct_receita_rifa": pct_receita(relatorio["receita_rifa"]),
        "pct_receita_patrocinios": pct_receita(relatorio["receita_patrocinios"]),
        "pct_receita_leilao": pct_receita(relatorio["receita_leilao"]),
        "pct_receita_outras": pct_receita(relatorio["receita_outras"]),
    }


def totais_notas_fiscais(db: Session, festejo_id: int) -> dict:
    notas = db.query(NotaFiscal).filter(NotaFiscal.festejo_id == festejo_id).all()
    total = sum(n.valor_total for n in notas)
    return {"quantidade": len(notas), "total": round(total, 2)}


def analise_despesas_festejo(db: Session, festejo_id: int) -> dict:
    """Agrega notas fiscais por categoria, dia e fornecedor (local de compra)."""
    notas = db.query(NotaFiscal).filter(NotaFiscal.festejo_id == festejo_id).all()
    total = sum(n.valor_total for n in notas)

    cat_map: dict[str, dict] = {}
    dia_map: dict[date, dict] = {}
    forn_map: dict[str, dict] = {}

    for nota in notas:
        cat = (nota.categoria or "Despesas gerais").strip()
        if cat not in cat_map:
            cat_map[cat] = {"categoria": cat, "valor": 0.0, "quantidade": 0}
        cat_map[cat]["valor"] += nota.valor_total
        cat_map[cat]["quantidade"] += 1

        dia = nota.data_emissao
        if dia:
            if dia not in dia_map:
                dia_map[dia] = {"data": dia, "valor": 0.0, "quantidade": 0}
            dia_map[dia]["valor"] += nota.valor_total
            dia_map[dia]["quantidade"] += 1

        forn = (nota.emitente_nome or "Fornecedor não informado").strip()
        chave_forn = forn.lower()
        if chave_forn not in forn_map:
            forn_map[chave_forn] = {"fornecedor": forn, "valor": 0.0, "quantidade": 0}
        forn_map[chave_forn]["valor"] += nota.valor_total
        forn_map[chave_forn]["quantidade"] += 1

    def _enriquecer(items: list[dict]) -> list[dict]:
        for item in items:
            item["valor"] = round(item["valor"], 2)
            item["pct"] = round((item["valor"] / total * 100), 1) if total else 0.0
            if "data" in item and item.get("data"):
                item["data_label"] = item["data"].strftime("%d/%m/%Y")
        return items

    por_categoria = _enriquecer(
        sorted(cat_map.values(), key=lambda x: (-x["valor"], x["categoria"].lower()))
    )
    por_dia = _enriquecer(
        sorted(dia_map.values(), key=lambda x: (-x["valor"], x["data"]))
    )
    por_fornecedor = _enriquecer(
        sorted(forn_map.values(), key=lambda x: (-x["valor"], x["fornecedor"].lower()))
    )

    dia_destaque = por_dia[0] if por_dia else None
    fornecedor_destaque = por_fornecedor[0] if por_fornecedor else None

    return {
        "total": round(total, 2),
        "quantidade": len(notas),
        "por_categoria": por_categoria,
        "por_dia": por_dia,
        "por_fornecedor": por_fornecedor[:10],
        "dia_destaque": dia_destaque,
        "fornecedor_destaque": fornecedor_destaque,
    }


def _descricao_lancamento_nota(parsed: NFeParsed) -> str:
    emitente = parsed.emitente_nome[:80] if parsed.emitente_nome else "Fornecedor"
    return f"{emitente} — NF {parsed.numero}/{parsed.serie}"


def _gerar_chave_manual(db: Session, festejo_id: int) -> str:
    seq = (
        db.query(NotaFiscal)
        .filter(NotaFiscal.festejo_id == festejo_id, NotaFiscal.chave.like("MAN%"))
        .count()
        + 1
    )
    while True:
        chave = f"MAN{festejo_id:06d}{seq:06d}{'0' * 29}"
        if not db.query(NotaFiscal).filter(NotaFiscal.chave == chave).first():
            return chave
        seq += 1


def is_nota_manual(chave: str) -> bool:
    return bool(chave) and chave.startswith("MAN") and len(chave) == 44


def cadastrar_nota_manual(
    db: Session,
    festejo_id: int,
    *,
    emitente_nome: str,
    valor_total: float,
    categoria: str,
    natureza_operacao: str = "",
    numero: str = "",
    serie: str = "1",
    emitente_cnpj: str = "",
    data_emissao: date | None = None,
    chave: str = "",
    produtos_resumo: str = "",
) -> NotaFiscal:
    emitente_nome = emitente_nome.strip()
    if not emitente_nome:
        raise ValueError("Informe o nome do emitente ou fornecedor.")
    if valor_total <= 0:
        raise ValueError("Informe um valor maior que zero.")

    chave_norm = validar_chave(chave) if chave.strip() else _gerar_chave_manual(db, festejo_id)
    existente = db.query(NotaFiscal).filter(NotaFiscal.chave == chave_norm).first()
    if existente:
        raise NotaDuplicadaError(existente)

    cat = categoria.strip()
    if not cat:
        cat = classificar_categoria(natureza_operacao, [produtos_resumo] if produtos_resumo else [], [])

    cnpj = "".join(c for c in emitente_cnpj if c.isdigit())

    parsed = NFeParsed(
        chave=chave_norm,
        numero=numero.strip() or "S/N",
        serie=serie.strip() or "1",
        modelo="99",
        emitente_nome=emitente_nome[:200],
        emitente_cnpj=cnpj[:20],
        data_emissao=data_emissao,
        natureza_operacao=(natureza_operacao.strip() or "Lançamento manual")[:255],
        valor_total=round(valor_total, 2),
        categoria=cat[:120],
        produtos_resumo=produtos_resumo.strip()[:500],
        completa=True,
    )
    return importar_nota_fiscal(db, festejo_id, parsed, xml_arquivo=None)


class NotaDuplicadaError(ValueError):
    """NF-e já cadastrada — importação/lançamento bloqueado."""

    def __init__(self, existente: "NotaFiscal"):
        self.existente = existente
        motivo = (
            f"Motivo: duplicidade — a NF {existente.numero}/{existente.serie} "
            f"({existente.emitente_nome}) já está cadastrada no sistema."
        )
        super().__init__(motivo)


def assert_nota_nao_duplicada(db: Session, chave: str) -> None:
    existente = db.query(NotaFiscal).filter(NotaFiscal.chave == chave).first()
    if existente:
        raise NotaDuplicadaError(existente)


def importar_nota_fiscal(
    db: Session,
    festejo_id: int,
    parsed: NFeParsed,
    xml_arquivo: str | None = None,
    sobrescrever_pendente: bool = False,
) -> NotaFiscal:
    existente = db.query(NotaFiscal).filter(NotaFiscal.chave == parsed.chave).first()
    if existente:
        if existente.completa or not sobrescrever_pendente:
            assert_nota_nao_duplicada(db, parsed.chave)
        if existente.lancamento_id:
            db.delete(existente.lancamento)
        db.delete(existente)
        db.flush()

    if not parsed.completa:
        raise ValueError(
            "Importação apenas pela chave não traz valor e natureza completos. "
            "Envie o arquivo XML da nota fiscal."
        )

    lancamento = LancamentoFinanceiro(
        festejo_id=festejo_id,
        tipo="despesa",
        categoria=parsed.categoria,
        descricao=_descricao_lancamento_nota(parsed),
        valor=parsed.valor_total,
    )
    db.add(lancamento)
    db.flush()

    nota = NotaFiscal(
        festejo_id=festejo_id,
        lancamento_id=lancamento.id,
        chave=parsed.chave,
        numero=parsed.numero,
        serie=parsed.serie,
        modelo=parsed.modelo,
        emitente_nome=parsed.emitente_nome,
        emitente_cnpj=parsed.emitente_cnpj,
        data_emissao=parsed.data_emissao,
        natureza_operacao=parsed.natureza_operacao,
        categoria=parsed.categoria,
        valor_total=parsed.valor_total,
        produtos_resumo=parsed.produtos_resumo,
        cfop_principal=parsed.cfop_principal,
        xml_arquivo=xml_arquivo,
        completa=parsed.completa,
    )
    db.add(nota)
    db.commit()
    db.refresh(nota)
    return nota


def excluir_nota_fiscal(db: Session, nota_id: int) -> None:
    nota = db.get(NotaFiscal, nota_id)
    if not nota:
        raise ValueError("Nota fiscal não encontrada.")
    investimento = (
        db.query(Investimento).filter(Investimento.nota_id == nota_id).first()
    )
    if investimento:
        db.delete(investimento)
    if nota.lancamento_id:
        lanc = db.get(LancamentoFinanceiro, nota.lancamento_id)
        if lanc:
            db.delete(lanc)
    db.delete(nota)
    db.commit()


def excluir_rifa_movimento(db: Session, mov_id: int, festejo_id: int) -> None:
    mov = db.get(RifaMovimento, mov_id)
    if not mov or mov.festejo_id != festejo_id:
        raise ValueError("Lançamento de rifa não encontrado.")
    db.delete(mov)
    db.commit()


def atualizar_rifa_movimento(
    db: Session,
    mov_id: int,
    festejo_id: int,
    *,
    descricao: str = "",
    valor: float,
    vendedor: str = "",
    data_mov: date | None = None,
) -> RifaMovimento:
    mov = db.get(RifaMovimento, mov_id)
    if not mov or mov.festejo_id != festejo_id:
        raise ValueError("Lançamento de rifa não encontrado.")
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")

    nome_vendedor = vendedor.strip() or mov.vendedor
    if mov.categoria == "venda":
        nome = nome_vendedor or descricao.strip() or mov.vendedor or "Vendedor"
        mov.vendedor = nome
        mov.descricao = f"Vendas — {nome}"
    elif mov.categoria == "premiacao":
        nome = nome_vendedor or descricao.strip() or mov.vendedor or "Vendedor"
        mov.vendedor = nome
        mov.descricao = f"Premiação — {nome}"
    elif descricao.strip():
        mov.descricao = descricao.strip()

    mov.valor = round(valor, 2)
    if data_mov:
        mov.data = data_mov
    db.commit()
    db.refresh(mov)
    return mov


def excluir_patrocinio_movimento(db: Session, mov_id: int, festejo_id: int) -> None:
    mov = db.get(PatrocinioMovimento, mov_id)
    if not mov or mov.festejo_id != festejo_id:
        raise ValueError("Lançamento de patrocínio não encontrado.")
    db.delete(mov)
    db.commit()


def atualizar_patrocinio_movimento(
    db: Session,
    mov_id: int,
    festejo_id: int,
    *,
    tipo: str,
    patrocinador: str = "",
    descricao: str = "",
    valor: float,
    data_mov: date | None = None,
) -> PatrocinioMovimento:
    mov = db.get(PatrocinioMovimento, mov_id)
    if not mov or mov.festejo_id != festejo_id:
        raise ValueError("Lançamento de patrocínio não encontrado.")
    if tipo not in ("entrada", "saida"):
        raise ValueError("Tipo inválido.")
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")

    mov.tipo = tipo
    nome = patrocinador.strip() or None
    texto = descricao.strip()
    if tipo == "entrada":
        if not nome and not texto:
            raise ValueError("Informe o patrocinador ou uma descrição.")
        mov.patrocinador = nome or texto
        mov.descricao = texto or nome or "Patrocínio"
    else:
        mov.patrocinador = nome
        mov.descricao = texto or "Saída de patrocínio"

    mov.valor = round(valor, 2)
    if data_mov:
        mov.data = data_mov
    db.commit()
    db.refresh(mov)
    return mov


def excluir_leilao_movimento(db: Session, mov_id: int) -> int:
    mov = db.get(LeilaoMovimento, mov_id)
    if not mov:
        raise ValueError("Lançamento de leilão não encontrado.")
    dia_id = mov.dia_id
    db.delete(mov)
    db.commit()
    return dia_id


def atualizar_leilao_movimento(
    db: Session,
    mov_id: int,
    *,
    tipo: str,
    descricao: str,
    valor: float,
) -> LeilaoMovimento:
    mov = db.get(LeilaoMovimento, mov_id)
    if not mov:
        raise ValueError("Lançamento de leilão não encontrado.")
    if tipo not in ("entrada", "saida"):
        raise ValueError("Tipo inválido.")
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")
    mov.tipo = tipo
    mov.descricao = descricao.strip()
    mov.valor = round(valor, 2)
    db.commit()
    db.refresh(mov)
    return mov


def excluir_sangria(db: Session, sangria_id: int) -> int:
    sangria = db.get(Sangria, sangria_id)
    if not sangria:
        raise ValueError("Sangria não encontrada.")
    dia_id = sangria.dia_id
    db.delete(sangria)
    db.commit()
    return dia_id


def atualizar_sangria(
    db: Session,
    sangria_id: int,
    *,
    destino: str,
    valor: float,
) -> Sangria:
    sangria = db.get(Sangria, sangria_id)
    if not sangria:
        raise ValueError("Sangria não encontrada.")
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")
    sangria.destino = destino.strip()
    sangria.valor = round(valor, 2)
    db.commit()
    db.refresh(sangria)
    return sangria


def excluir_lancamento_financeiro(db: Session, lanc_id: int, festejo_id: int) -> None:
    lanc = db.get(LancamentoFinanceiro, lanc_id)
    if not lanc or lanc.festejo_id != festejo_id:
        raise ValueError("Lançamento não encontrado.")
    if lanc.nota_fiscal:
        raise ValueError("Despesa vinculada a nota fiscal — edite ou exclua em Despesas.")
    db.delete(lanc)
    db.commit()


def atualizar_lancamento_financeiro(
    db: Session,
    lanc_id: int,
    festejo_id: int,
    *,
    tipo: str,
    categoria: str,
    descricao: str,
    valor: float,
) -> LancamentoFinanceiro:
    lanc = db.get(LancamentoFinanceiro, lanc_id)
    if not lanc or lanc.festejo_id != festejo_id:
        raise ValueError("Lançamento não encontrado.")
    if lanc.nota_fiscal:
        raise ValueError("Despesa vinculada a nota fiscal — edite em Despesas.")
    if tipo not in ("receita", "despesa"):
        raise ValueError("Tipo inválido.")
    if valor <= 0:
        raise ValueError("Informe um valor maior que zero.")
    lanc.tipo = tipo
    lanc.categoria = categoria.strip()
    lanc.descricao = descricao.strip()
    lanc.valor = round(valor, 2)
    db.commit()
    db.refresh(lanc)
    return lanc


def atualizar_nota_fiscal(
    db: Session,
    nota_id: int,
    festejo_id: int,
    *,
    emitente_nome: str,
    valor_total: float,
    categoria: str,
    natureza_operacao: str = "",
    numero: str = "",
    serie: str = "1",
    emitente_cnpj: str = "",
    data_emissao: date | None = None,
    produtos_resumo: str = "",
) -> NotaFiscal:
    nota = db.get(NotaFiscal, nota_id)
    if not nota or nota.festejo_id != festejo_id:
        raise ValueError("Nota fiscal não encontrada.")
    if valor_total <= 0:
        raise ValueError("Informe um valor maior que zero.")

    nota.emitente_nome = emitente_nome.strip()[:200]
    nota.valor_total = round(valor_total, 2)
    nota.categoria = categoria.strip()[:120]
    nota.natureza_operacao = (natureza_operacao.strip() or nota.natureza_operacao)[:255]
    nota.numero = numero.strip() or nota.numero
    nota.serie = serie.strip() or nota.serie
    nota.emitente_cnpj = "".join(c for c in emitente_cnpj if c.isdigit())[:20]
    nota.data_emissao = data_emissao
    nota.produtos_resumo = produtos_resumo.strip()[:500]

    if nota.lancamento_id:
        lanc = db.get(LancamentoFinanceiro, nota.lancamento_id)
        if lanc:
            lanc.categoria = nota.categoria
            lanc.valor = nota.valor_total
            lanc.descricao = f"{nota.emitente_nome[:80]} — NF {nota.numero}/{nota.serie}"

    db.commit()
    db.refresh(nota)
    return nota
