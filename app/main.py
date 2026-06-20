import shutil

import json

from datetime import date, datetime

from pathlib import Path

from urllib.parse import quote



from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile

from fastapi.responses import HTMLResponse, RedirectResponse, Response

from fastapi.staticfiles import StaticFiles

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from sqlalchemy.orm import Session, joinedload



from app.database import DATA_DIR, Base, engine, get_db

from app.models import (

    FORMAS_PAGAMENTO,

    DiaFestejo,

    Festejo,

    Investimento,

    LancamentoFinanceiro,

    LeilaoMovimento,

    ProdutoVenda,

    RelatorioPdf,

    RifaMovimento,

    Sangria,

    NotaFiscal,

    PatrocinioMovimento,

)

from app.pdf_parser import parse_money, parse_pdf_file

from app.services import (

    calc_consolidacao_dia,

    ensure_caixa_dia,

    get_dia_completo,

    get_or_create_festejo_ativo,

    migrar_para_caixa_unico,

    migrar_rifa_campos,

    resumo_vendedores_rifa,

    importar_planilha_rifa,

    listar_caixa_festejo,

    ranking_produtos_vendas,
    resumo_gratuidade_festejo,

    relatorio_final,

    dados_infografico,

    sincronizar_pdf_para_caixa,

    totais_leilao,

    totais_patrocinios,

    resumo_patrocinadores,

    totais_investimentos,

    mapa_investimentos_por_nota,

    resumo_investimentos_por_item,

    criar_investimento,

    totais_rifa,

    importar_nota_fiscal,

    assert_nota_nao_duplicada,

    NotaDuplicadaError,

    cadastrar_nota_manual,

    excluir_nota_fiscal,

    atualizar_nota_fiscal,

    excluir_rifa_movimento,

    atualizar_rifa_movimento,

    excluir_patrocinio_movimento,

    atualizar_patrocinio_movimento,

    excluir_investimento,

    atualizar_investimento,

    excluir_leilao_movimento,

    atualizar_leilao_movimento,

    excluir_sangria,

    atualizar_sangria,

    excluir_lancamento_financeiro,

    atualizar_lancamento_financeiro,

    totais_notas_fiscais,

    analise_despesas_festejo,

    is_nota_manual,

)



from app.nfe_parser import CATEGORIAS_KEYWORDS, parse_chave_nfe, parse_nfe_xml, validar_chave
from app.nfe_pdf_parser import parse_nfe_pdf
from app.rifa_xlsx_parser import parse_rifa_xlsx
from app.csv_export import SECOES_DISPONIVEIS, gerar_csv_relatorio



BASE_DIR = Path(__file__).resolve().parent.parent

TEMPLATES_DIR = BASE_DIR / "templates"

STATIC_DIR = BASE_DIR / "static"



Base.metadata.create_all(bind=engine)



app = FastAPI(title="Festejo Financeiro")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))





def fmt_money(value: float | None) -> str:

    if value is None:

        return "R$ 0,00"

    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")





templates.env.filters["money"] = fmt_money

templates.env.filters["datebr"] = lambda d: d.strftime("%d/%m/%Y") if d else ""

templates.env.filters["nota_manual"] = is_nota_manual

templates.env.filters["abs"] = abs

templates.env.filters["tojson"] = lambda v: Markup(json.dumps(v, ensure_ascii=False))


def _section_subnav(base_path: str, lancar_label: str) -> list[dict]:
    return [
        {"id": "visao", "label": "Visão geral", "url": f"{base_path}/visao-geral", "icon": "bi-grid-1x2"},
        {"id": "lancar", "label": lancar_label, "url": f"{base_path}/lancar", "icon": "bi-plus-circle"},
    ]





@app.on_event("startup")

def seed_defaults():

    db = Session(bind=engine)

    try:

        get_or_create_festejo_ativo(db)

        migrar_para_caixa_unico(db)

        migrar_rifa_campos(db)

    finally:

        db.close()





@app.get("/", response_class=HTMLResponse)

def dashboard(request: Request, db: Session = Depends(get_db)):

    festejo = get_or_create_festejo_ativo(db)

    relatorio = relatorio_final(db, festejo.id)

    return templates.TemplateResponse(

        request,

        "dashboard.html",

        {

            "festejo": festejo,

            "relatorio": relatorio,

        },

    )





@app.post("/festejo/config")

def atualizar_festejo(

    nome: str = Form(...),

    ano: int = Form(...),

    data_inicio: str = Form(""),

    data_fim: str = Form(""),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    festejo.nome = nome

    festejo.ano = ano

    festejo.data_inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date() if data_inicio else None

    festejo.data_fim = datetime.strptime(data_fim, "%Y-%m-%d").date() if data_fim else None

    db.commit()

    return RedirectResponse("/", status_code=303)





@app.post("/dias/novo")

def criar_dia(

    data: str = Form(...),

    rotulo: str = Form(""),

    numero_dia: int = Form(0),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    dia_data = datetime.strptime(data, "%Y-%m-%d").date()

    existente = (

        db.query(DiaFestejo)

        .filter(DiaFestejo.festejo_id == festejo.id, DiaFestejo.data == dia_data)

        .first()

    )

    if existente:

        return RedirectResponse(f"/caixa/dias/{existente.id}", status_code=303)



    dia = DiaFestejo(

        festejo_id=festejo.id,

        data=dia_data,

        rotulo=rotulo or None,

        numero_dia=numero_dia or None,

    )

    db.add(dia)

    db.commit()

    db.refresh(dia)

    ensure_caixa_dia(db, dia)

    return RedirectResponse(f"/caixa/dias/{dia.id}", status_code=303)





@app.get("/caixa", response_class=HTMLResponse)
def pagina_caixa_redirect():
    return RedirectResponse("/caixa/visao-geral", status_code=303)


@app.get("/caixa/visao-geral", response_class=HTMLResponse)
@app.get("/caixa/lancar", response_class=HTMLResponse)
def pagina_caixa(request: Request, db: Session = Depends(get_db)):
    festejo = get_or_create_festejo_ativo(db)
    resumo = listar_caixa_festejo(db, festejo.id)
    ranking = ranking_produtos_vendas(db, festejo.id)
    gratuidade = resumo_gratuidade_festejo(db, festejo.id)
    view = "lancar" if request.url.path.endswith("/lancar") else "visao"

    return templates.TemplateResponse(
        request,
        "caixa.html",
        {
            "festejo": festejo,
            "dias": resumo["dias"],
            "totais": resumo["totais"],
            "ranking": ranking,
            "gratuidade": gratuidade,
            "view": view,
            "subnav": _section_subnav("/caixa", "Lançar caixa"),
        },
    )





@app.get("/caixa/dias/{dia_id}", response_class=HTMLResponse)

def ver_caixa_dia(dia_id: int, request: Request, db: Session = Depends(get_db)):

    dia = get_dia_completo(db, dia_id)

    if not dia:

        raise HTTPException(404, "Dia não encontrado")

    ensure_caixa_dia(db, dia)

    dia = get_dia_completo(db, dia_id)

    consolidacao = calc_consolidacao_dia(dia)

    return templates.TemplateResponse(

        request,

        "caixa_dia.html",

        {

            "dia": dia,

            "consolidacao": consolidacao,

            "formas_pagamento": FORMAS_PAGAMENTO,

        },

    )





@app.get("/dias/{dia_id}")

def ver_dia_redirect(dia_id: int):

    return RedirectResponse(f"/caixa/dias/{dia_id}", status_code=303)





@app.post("/dias/{dia_id}/pdf")

async def importar_pdf_dia(

    dia_id: int,

    arquivo: UploadFile = File(...),

    db: Session = Depends(get_db),

):

    dia = get_dia_completo(db, dia_id)

    if not dia:

        raise HTTPException(404, "Dia não encontrado")



    upload_path = DATA_DIR / "uploads" / f"{dia_id}_{arquivo.filename}"

    with upload_path.open("wb") as buffer:

        shutil.copyfileobj(arquivo.file, buffer)



    parsed = parse_pdf_file(str(upload_path))



    if dia.relatorio_pdf:

        db.delete(dia.relatorio_pdf)

        db.flush()



    relatorio = RelatorioPdf(

        dia_id=dia.id,

        festejo_id=dia.festejo_id,

        arquivo_nome=arquivo.filename,

        data_inicio=parsed.data_inicio,

        data_fim=parsed.data_fim,

        eh_acumulado=parsed.eh_acumulado,

        dinheiro=parsed.dinheiro,

        credito=parsed.credito,

        debito=parsed.debito,

        pix=parsed.pix,

        total_vendas=parsed.total_vendas,

        total_gratuidade=parsed.total_gratuidade,

        total_geral=parsed.total_geral,

    )

    db.add(relatorio)

    db.flush()



    for produto in parsed.produtos:

        db.add(

            ProdutoVenda(

                relatorio_id=relatorio.id,

                secao=produto.secao,

                codigo=produto.codigo,

                produto=produto.produto,

                quantidade=produto.quantidade,

                valor_unitario=produto.valor_unitario,

                total=produto.total,

            )

        )



    ensure_caixa_dia(db, dia)

    dia = get_dia_completo(db, dia_id)

    if not parsed.eh_acumulado:

        sincronizar_pdf_para_caixa(dia, relatorio, sobrescrever=True)



    db.commit()

    return RedirectResponse(f"/caixa/dias/{dia_id}", status_code=303)





@app.post("/dias/{dia_id}/pdf/sincronizar")

def sincronizar_pdf_caixa_route(dia_id: int, db: Session = Depends(get_db)):

    dia = get_dia_completo(db, dia_id)

    if not dia or not dia.relatorio_pdf:

        raise HTTPException(404, "Dia ou PDF não encontrado")

    if dia.relatorio_pdf.eh_acumulado:

        raise HTTPException(400, "PDF acumulado não pode ser sincronizado em um dia")

    ensure_caixa_dia(db, dia)

    sincronizar_pdf_para_caixa(dia, dia.relatorio_pdf, sobrescrever=True)

    db.commit()

    return RedirectResponse(f"/caixa/dias/{dia_id}#consolidacao", status_code=303)





@app.post("/dias/{dia_id}/caixa/salvar")

async def salvar_caixa(request: Request, dia_id: int, db: Session = Depends(get_db)):

    form = await request.form()

    dia = get_dia_completo(db, dia_id)

    if not dia:

        raise HTTPException(404, "Dia não encontrado")



    caixa = ensure_caixa_dia(db, dia)

    caixa.troco = float(form.get("troco") or 0)

    caixa.dinheiro = float(form.get("dinheiro") or 0)

    caixa.debito = float(form.get("debito") or 0)

    caixa.credito = float(form.get("credito") or 0)

    caixa.pix = float(form.get("pix") or 0)

    caixa.leilao_pago_caixa = float(form.get("leilao_pago_caixa") or 0)



    db.commit()

    return RedirectResponse(f"/caixa/dias/{dia_id}#caixa", status_code=303)





@app.post("/dias/{dia_id}/leilao")

def adicionar_leilao(

    dia_id: int,

    tipo: str = Form(...),

    descricao: str = Form(""),

    valor: float = Form(...),

    db: Session = Depends(get_db),

):

    if tipo not in ("entrada", "saida"):

        raise HTTPException(400, "Tipo inválido")

    db.add(LeilaoMovimento(dia_id=dia_id, tipo=tipo, descricao=descricao, valor=valor))

    db.commit()

    return RedirectResponse(f"/leilao/dias/{dia_id}", status_code=303)





@app.post("/leilao/{mov_id}/excluir")

def excluir_leilao(mov_id: int, voltar: str = Form(""), db: Session = Depends(get_db)):

    try:

        dia_id = excluir_leilao_movimento(db, mov_id)

    except ValueError:

        raise HTTPException(404)

    if voltar == "leilao":

        return RedirectResponse("/leilao/lancar", status_code=303)

    return RedirectResponse(f"/leilao/dias/{dia_id}", status_code=303)





@app.post("/leilao/{mov_id}/editar")

def editar_leilao(

    mov_id: int,

    tipo: str = Form(...),

    descricao: str = Form(...),

    valor: str = Form(...),

    voltar: str = Form(""),

    db: Session = Depends(get_db),

):

    mov = db.get(LeilaoMovimento, mov_id)

    if not mov:

        raise HTTPException(404)

    try:

        atualizar_leilao_movimento(

            db, mov_id, tipo=tipo, descricao=descricao, valor=parse_money(valor)

        )

    except ValueError as exc:

        raise HTTPException(400, str(exc))

    if voltar == "leilao":

        return RedirectResponse("/leilao/lancar", status_code=303)

    return RedirectResponse(f"/leilao/dias/{mov.dia_id}", status_code=303)





@app.get("/rifa", response_class=HTMLResponse)
def pagina_rifa_redirect():
    return RedirectResponse("/rifa/visao-geral", status_code=303)


@app.get("/rifa/visao-geral", response_class=HTMLResponse)
@app.get("/rifa/lancar", response_class=HTMLResponse)
def pagina_rifa(request: Request, db: Session = Depends(get_db), erro: str = "", sucesso: str = ""):
    festejo = get_or_create_festejo_ativo(db)
    view = "lancar" if request.url.path.endswith("/lancar") else "visao"

    movimentos = (
        db.query(RifaMovimento)
        .filter(RifaMovimento.festejo_id == festejo.id)
        .order_by(RifaMovimento.data.desc(), RifaMovimento.id.desc())
        .all()
    )

    totais = totais_rifa(db, festejo.id)

    return templates.TemplateResponse(
        request,
        "rifa.html",
        {
            "festejo": festejo,
            "movimentos": movimentos,
            "totais": totais,
            "vendedores": resumo_vendedores_rifa(db, festejo.id),
            "erro": erro,
            "sucesso": sucesso,
            "view": view,
            "subnav": _section_subnav("/rifa", "Lançar rifa"),
        },
    )





@app.post("/rifa/importar")

async def importar_planilha_rifa_route(

    request: Request,

    arquivo: UploadFile = File(...),

    substituir: str = Form("sim"),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    erro = ""

    sucesso = ""

    try:

        if not arquivo.filename or not arquivo.filename.lower().endswith((".xlsx", ".xlsm")):

            raise ValueError("Envie a planilha Excel (.xlsx) de prestação de contas das rifas.")

        dest = DATA_DIR / "uploads" / f"rifa_{festejo.id}_{arquivo.filename}"

        content = await arquivo.read()

        dest.write_bytes(content)

        planilha = parse_rifa_xlsx(dest)

        criados = importar_planilha_rifa(db, festejo.id, planilha, substituir=substituir == "sim")

        sucesso = (

            f"Planilha importada: {criados['doacoes']} doações, {criados['despesas']} despesas, "

            f"{criados['vendas']} vendedores, {criados['premiacoes']} premiações."

        )

    except ValueError as exc:

        erro = str(exc)

    except Exception as exc:

        erro = f"Erro ao importar planilha: {exc}"



    movimentos = (

        db.query(RifaMovimento)

        .filter(RifaMovimento.festejo_id == festejo.id)

        .order_by(RifaMovimento.data.desc(), RifaMovimento.id.desc())

        .all()

    )

    return templates.TemplateResponse(
        request,
        "rifa.html",
        {
            "festejo": festejo,
            "movimentos": movimentos,
            "totais": totais_rifa(db, festejo.id),
            "vendedores": resumo_vendedores_rifa(db, festejo.id),
            "erro": erro,
            "sucesso": sucesso,
            "view": "lancar",
            "subnav": _section_subnav("/rifa", "Lançar rifa"),
        },
    )





@app.post("/rifa")

def adicionar_rifa(

    categoria: str = Form(...),

    descricao: str = Form(""),

    valor: str = Form(...),

    vendedor: str = Form(""),

    data: str = Form(""),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    if categoria not in ("doacao", "despesa", "venda", "premiacao", "outro"):

        raise HTTPException(400, "Categoria inválida")

    valor_num = parse_money(valor)

    if valor_num <= 0:

        raise HTTPException(400, "Informe um valor maior que zero")

    tipo = "entrada" if categoria in ("doacao", "venda", "outro") else "saida"

    if categoria in ("venda", "premiacao") and not vendedor.strip() and not descricao.strip():

        raise HTTPException(400, "Informe o nome do vendedor")

    data_mov = datetime.strptime(data, "%Y-%m-%d").date() if data else date.today()

    nome_vendedor = vendedor.strip() or None

    texto = descricao.strip()

    if categoria == "doacao" and not texto:

        texto = "Doação"

    if categoria == "despesa" and not texto:

        texto = "Despesa"

    if categoria == "venda":

        nome = nome_vendedor or texto

        texto = f"Vendas — {nome}"

        nome_vendedor = nome

    if categoria == "premiacao":

        nome = nome_vendedor or texto

        texto = f"Premiação — {nome}"

        nome_vendedor = nome

    db.add(

        RifaMovimento(

            festejo_id=festejo.id,

            tipo=tipo,

            categoria=categoria,

            vendedor=nome_vendedor,

            descricao=texto,

            valor=valor_num,

            data=data_mov,

        )

    )

    db.commit()

    return RedirectResponse("/rifa/lancar", status_code=303)





@app.post("/rifa/{mov_id}/editar")

def editar_rifa(

    mov_id: int,

    descricao: str = Form(""),

    valor: str = Form(...),

    vendedor: str = Form(""),

    data: str = Form(""),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    data_mov = datetime.strptime(data, "%Y-%m-%d").date() if data else None

    try:

        atualizar_rifa_movimento(

            db,

            mov_id,

            festejo.id,

            descricao=descricao,

            valor=parse_money(valor),

            vendedor=vendedor,

            data_mov=data_mov,

        )

    except ValueError as exc:

        raise HTTPException(400, str(exc))

    return RedirectResponse("/rifa/lancar", status_code=303)





@app.post("/rifa/{mov_id}/excluir")

def excluir_rifa(mov_id: int, db: Session = Depends(get_db)):

    festejo = get_or_create_festejo_ativo(db)

    try:

        excluir_rifa_movimento(db, mov_id, festejo.id)

    except ValueError:

        pass

    return RedirectResponse("/rifa/lancar", status_code=303)


@app.get("/patrocinios", response_class=HTMLResponse)
def pagina_patrocinios_redirect():
    return RedirectResponse("/patrocinios/visao-geral", status_code=303)


@app.get("/patrocinios/visao-geral", response_class=HTMLResponse)
@app.get("/patrocinios/lancar", response_class=HTMLResponse)
def pagina_patrocinios(request: Request, db: Session = Depends(get_db), erro: str = "", sucesso: str = ""):
    festejo = get_or_create_festejo_ativo(db)
    view = "lancar" if request.url.path.endswith("/lancar") else "visao"

    movimentos = (
        db.query(PatrocinioMovimento)
        .filter(PatrocinioMovimento.festejo_id == festejo.id)
        .order_by(PatrocinioMovimento.data.desc(), PatrocinioMovimento.id.desc())
        .all()
    )

    return templates.TemplateResponse(
        request,
        "patrocinios.html",
        {
            "festejo": festejo,
            "movimentos": movimentos,
            "totais": totais_patrocinios(db, festejo.id),
            "patrocinadores": resumo_patrocinadores(db, festejo.id),
            "erro": erro,
            "sucesso": sucesso,
            "view": view,
            "subnav": _section_subnav("/patrocinios", "Lançar patrocínios"),
        },
    )


@app.post("/patrocinios")
def adicionar_patrocinio(
    tipo: str = Form(...),
    patrocinador: str = Form(""),
    descricao: str = Form(""),
    valor: str = Form(...),
    data: str = Form(""),
    db: Session = Depends(get_db),
):
    festejo = get_or_create_festejo_ativo(db)

    if tipo not in ("entrada", "saida"):
        raise HTTPException(400, "Tipo inválido")

    valor_num = parse_money(valor)
    if valor_num <= 0:
        raise HTTPException(400, "Informe um valor maior que zero")

    nome = patrocinador.strip() or None
    texto = descricao.strip()
    if tipo == "entrada" and not nome and not texto:
        raise HTTPException(400, "Informe o patrocinador ou uma descrição")

    if tipo == "entrada":
        patrocinador_final = nome or texto
        descricao_final = texto or nome or "Patrocínio"
    else:
        patrocinador_final = nome
        descricao_final = texto or "Saída de patrocínio"

    data_mov = datetime.strptime(data, "%Y-%m-%d").date() if data else date.today()

    db.add(
        PatrocinioMovimento(
            festejo_id=festejo.id,
            tipo=tipo,
            patrocinador=patrocinador_final,
            descricao=descricao_final,
            valor=valor_num,
            data=data_mov,
        )
    )
    db.commit()
    return RedirectResponse("/patrocinios/lancar", status_code=303)


@app.post("/patrocinios/{mov_id}/editar")
def editar_patrocinio(
    mov_id: int,
    tipo: str = Form(...),
    patrocinador: str = Form(""),
    descricao: str = Form(""),
    valor: str = Form(...),
    data: str = Form(""),
    db: Session = Depends(get_db),
):
    festejo = get_or_create_festejo_ativo(db)
    data_mov = datetime.strptime(data, "%Y-%m-%d").date() if data else None

    try:
        atualizar_patrocinio_movimento(
            db,
            mov_id,
            festejo.id,
            tipo=tipo,
            patrocinador=patrocinador,
            descricao=descricao,
            valor=parse_money(valor),
            data_mov=data_mov,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return RedirectResponse("/patrocinios/lancar", status_code=303)


@app.post("/patrocinios/{mov_id}/excluir")
def excluir_patrocinio(mov_id: int, db: Session = Depends(get_db)):
    festejo = get_or_create_festejo_ativo(db)
    try:
        excluir_patrocinio_movimento(db, mov_id, festejo.id)
    except ValueError:
        pass
    return RedirectResponse("/patrocinios/lancar", status_code=303)


@app.get("/investimentos", response_class=HTMLResponse)
def pagina_investimentos_redirect():
    return RedirectResponse("/investimentos/visao-geral", status_code=303)


@app.get("/investimentos/visao-geral", response_class=HTMLResponse)
@app.get("/investimentos/lancar", response_class=HTMLResponse)
def pagina_investimentos(request: Request, db: Session = Depends(get_db), erro: str = "", sucesso: str = ""):
    festejo = get_or_create_festejo_ativo(db)
    view = "lancar" if request.url.path.endswith("/lancar") else "visao"

    investimentos = (
        db.query(Investimento)
        .options(joinedload(Investimento.nota_fiscal))
        .filter(Investimento.festejo_id == festejo.id)
        .order_by(Investimento.data.desc(), Investimento.id.desc())
        .all()
    )

    return templates.TemplateResponse(
        request,
        "investimentos.html",
        {
            "festejo": festejo,
            "investimentos": investimentos,
            "totais": totais_investimentos(db, festejo.id),
            "por_item": resumo_investimentos_por_item(db, festejo.id),
            "erro": erro,
            "sucesso": sucesso,
            "view": view,
            "subnav": _section_subnav("/investimentos", "Lançar investimentos"),
        },
    )


@app.post("/investimentos")
def adicionar_investimento(
    investido_em: str = Form(...),
    valor: str = Form(...),
    data: str = Form(""),
    observacao: str = Form(""),
    db: Session = Depends(get_db),
):
    festejo = get_or_create_festejo_ativo(db)
    data_inv = datetime.strptime(data, "%Y-%m-%d").date() if data else date.today()

    try:
        criar_investimento(
            db,
            festejo.id,
            investido_em=investido_em,
            valor=parse_money(valor),
            data_inv=data_inv,
            observacao=observacao,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return RedirectResponse("/investimentos/lancar", status_code=303)


@app.post("/investimentos/{inv_id}/editar")
def editar_investimento_route(
    inv_id: int,
    investido_em: str = Form(...),
    valor: str = Form(...),
    data: str = Form(""),
    observacao: str = Form(""),
    db: Session = Depends(get_db),
):
    festejo = get_or_create_festejo_ativo(db)
    data_inv = datetime.strptime(data, "%Y-%m-%d").date() if data else None

    try:
        atualizar_investimento(
            db,
            inv_id,
            festejo.id,
            investido_em=investido_em,
            valor=parse_money(valor),
            data_inv=data_inv,
            observacao=observacao,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return RedirectResponse("/investimentos/lancar", status_code=303)


@app.post("/investimentos/{inv_id}/excluir")
def excluir_investimento_route(inv_id: int, db: Session = Depends(get_db)):
    festejo = get_or_create_festejo_ativo(db)
    try:
        excluir_investimento(db, inv_id, festejo.id)
    except ValueError:
        pass
    return RedirectResponse("/investimentos/lancar", status_code=303)


@app.get("/leilao", response_class=HTMLResponse)
def pagina_leilao_redirect():
    return RedirectResponse("/leilao/visao-geral", status_code=303)


@app.get("/leilao/visao-geral", response_class=HTMLResponse)
@app.get("/leilao/lancar", response_class=HTMLResponse)
def pagina_leilao(request: Request, db: Session = Depends(get_db)):
    festejo = get_or_create_festejo_ativo(db)
    view = "lancar" if request.url.path.endswith("/lancar") else "visao"

    dias = (
        db.query(DiaFestejo)
        .filter(DiaFestejo.festejo_id == festejo.id)
        .order_by(DiaFestejo.data)
        .all()
    )

    movimentos = (
        db.query(LeilaoMovimento)
        .join(DiaFestejo)
        .filter(DiaFestejo.festejo_id == festejo.id)
        .order_by(DiaFestejo.data, LeilaoMovimento.id)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "leilao.html",
        {
            "festejo": festejo,
            "dias": dias,
            "movimentos": movimentos,
            "totais": totais_leilao(db, festejo.id),
            "view": view,
            "subnav": _section_subnav("/leilao", "Lançar leilão"),
        },
    )





@app.get("/leilao/dias/{dia_id}", response_class=HTMLResponse)

def ver_leilao_dia(dia_id: int, request: Request, db: Session = Depends(get_db)):

    dia = get_dia_completo(db, dia_id)

    if not dia:

        raise HTTPException(404, "Dia não encontrado")

    consolidacao = calc_consolidacao_dia(dia)

    return templates.TemplateResponse(

        request,

        "leilao_dia.html",

        {"dia": dia, "consolidacao": consolidacao},

    )





@app.get("/relatorio", response_class=HTMLResponse)
def pagina_relatorio_redirect():
    return RedirectResponse("/relatorio/visao-geral", status_code=303)


@app.get("/relatorio/visao-geral", response_class=HTMLResponse)
@app.get("/relatorio/lancar", response_class=HTMLResponse)
def pagina_relatorio(request: Request, db: Session = Depends(get_db)):
    festejo = get_or_create_festejo_ativo(db)
    dados = relatorio_final(db, festejo.id)
    dados["secoes_csv"] = SECOES_DISPONIVEIS
    dados["view"] = "lancar" if request.url.path.endswith("/lancar") else "visao"
    dados["subnav"] = _section_subnav("/relatorio", "Lançamentos")
    return templates.TemplateResponse(request, "relatorio.html", dados)





@app.get("/relatorio/exportar-csv")

def exportar_relatorio_csv(

    db: Session = Depends(get_db),

    secoes: list[str] = Query(default=[]),

):

    festejo = get_or_create_festejo_ativo(db)

    if secoes and "tudo" not in secoes:
        validas = [s for s in secoes if s in SECOES_DISPONIVEIS]
        if not validas:
            raise HTTPException(400, "Selecione ao menos uma seção para exportar.")
        secoes = validas

    conteudo, nome_arquivo = gerar_csv_relatorio(db, festejo.id, secoes)

    return Response(

        content=conteudo,

        media_type="text/csv; charset=utf-8",

        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},

    )





@app.get("/infografico", response_class=HTMLResponse)

def pagina_infografico(request: Request, db: Session = Depends(get_db)):

    festejo = get_or_create_festejo_ativo(db)

    dados = dados_infografico(db, festejo.id)

    dados["gerado_em"] = datetime.now().strftime("%d/%m/%Y às %H:%M")

    return templates.TemplateResponse(request, "infografico.html", dados)





@app.post("/relatorio/lancamento")

def adicionar_lancamento(

    tipo: str = Form(...),

    categoria: str = Form(...),

    descricao: str = Form(""),

    valor: float = Form(...),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    db.add(

        LancamentoFinanceiro(

            festejo_id=festejo.id,

            tipo=tipo,

            categoria=categoria,

            descricao=descricao,

            valor=valor,

        )

    )

    db.commit()

    return RedirectResponse("/relatorio/lancar", status_code=303)





@app.post("/relatorio/lancamento/{lanc_id}/editar")

def editar_lancamento_relatorio(

    lanc_id: int,

    tipo: str = Form(...),

    categoria: str = Form(...),

    descricao: str = Form(""),

    valor: str = Form(...),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    try:

        atualizar_lancamento_financeiro(

            db,

            lanc_id,

            festejo.id,

            tipo=tipo,

            categoria=categoria,

            descricao=descricao,

            valor=parse_money(valor),

        )

    except ValueError as exc:

        raise HTTPException(400, str(exc))

    return RedirectResponse("/relatorio/lancar", status_code=303)





@app.post("/relatorio/lancamento/{lanc_id}/excluir")

def excluir_lancamento_relatorio(lanc_id: int, db: Session = Depends(get_db)):

    festejo = get_or_create_festejo_ativo(db)

    try:

        excluir_lancamento_financeiro(db, lanc_id, festejo.id)

    except ValueError:

        pass

    return RedirectResponse("/relatorio/lancar", status_code=303)





@app.post("/dias/{dia_id}/sangria")

def adicionar_sangria(

    dia_id: int,

    destino: str = Form(""),

    valor: float = Form(...),

    db: Session = Depends(get_db),

):

    db.add(Sangria(dia_id=dia_id, destino=destino, valor=valor))

    db.commit()

    return RedirectResponse(f"/caixa/dias/{dia_id}#sangrias", status_code=303)





@app.post("/sangrias/{sangria_id}/editar")

def editar_sangria(

    sangria_id: int,

    destino: str = Form(...),

    valor: str = Form(...),

    db: Session = Depends(get_db),

):

    sangria = db.get(Sangria, sangria_id)

    if not sangria:

        raise HTTPException(404)

    try:

        atualizar_sangria(db, sangria_id, destino=destino, valor=parse_money(valor))

    except ValueError as exc:

        raise HTTPException(400, str(exc))

    return RedirectResponse(f"/caixa/dias/{sangria.dia_id}#sangrias", status_code=303)





@app.post("/sangrias/{sangria_id}/excluir")

def excluir_sangria_route(sangria_id: int, db: Session = Depends(get_db)):

    try:

        dia_id = excluir_sangria(db, sangria_id)

    except ValueError:

        raise HTTPException(404)

    return RedirectResponse(f"/caixa/dias/{dia_id}#sangrias", status_code=303)





@app.get("/api/dias/{dia_id}/consolidacao")

def api_consolidacao(dia_id: int, db: Session = Depends(get_db)):

    dia = get_dia_completo(db, dia_id)

    if not dia:

        raise HTTPException(404)

    return calc_consolidacao_dia(dia)





@app.get("/api/relatorio")

def api_relatorio(db: Session = Depends(get_db)):

    festejo = get_or_create_festejo_ativo(db)

    data = relatorio_final(db, festejo.id)

    data["festejo"] = {"id": data["festejo"].id, "nome": data["festejo"].nome, "ano": data["festejo"].ano}

    return data



def _parse_toast_query(request: Request) -> dict | None:
    toast_type = request.query_params.get("toast", "").strip()
    msg = request.query_params.get("msg", "").strip()
    if not toast_type or not msg:
        return None
    if toast_type not in ("success", "error", "info"):
        toast_type = "info"
    return {
        "type": toast_type,
        "msg": msg,
        "detalhe": request.query_params.get("detalhe", "").strip(),
    }


def _ctx_despesas(
    db: Session,
    festejo: Festejo,
    view: str = "visao",
    erro: str = "",
    sucesso: str = "",
    toast: dict | None = None,
) -> dict:
    notas = (
        db.query(NotaFiscal)
        .filter(NotaFiscal.festejo_id == festejo.id)
        .order_by(NotaFiscal.data_emissao.desc(), NotaFiscal.id.desc())
        .all()
    )
    return {
        "festejo": festejo,
        "notas": notas,
        "totais": totais_notas_fiscais(db, festejo.id),
        "analise": analise_despesas_festejo(db, festejo.id),
        "categorias": [c[0] for c in CATEGORIAS_KEYWORDS] + ["Despesas gerais"],
        "erro": erro,
        "sucesso": sucesso,
        "toast": toast,
        "view": view,
        "subnav": _section_subnav("/despesas", "Lançar despesas"),
        "investimentos_por_nota": mapa_investimentos_por_nota(db, festejo.id),
    }


@app.get("/despesas", response_class=HTMLResponse)
def pagina_despesas_redirect():
    return RedirectResponse("/despesas/visao-geral", status_code=303)


@app.get("/despesas/visao-geral", response_class=HTMLResponse)
@app.get("/despesas/lancar", response_class=HTMLResponse)
def pagina_despesas(request: Request, db: Session = Depends(get_db), erro: str = "", sucesso: str = ""):
    festejo = get_or_create_festejo_ativo(db)
    view = "lancar" if request.url.path.endswith("/lancar") else "visao"
    toast = _parse_toast_query(request)

    return templates.TemplateResponse(
        request,
        "despesas.html",
        _ctx_despesas(db, festejo, view, erro, sucesso, toast),
    )





@app.post("/despesas/importar")

async def importar_despesa_nfe(

    request: Request,

    chave: str = Form(""),

    arquivo_nota: UploadFile | None = File(None),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)



    try:

        arquivo_path = None

        parsed = None



        if arquivo_nota and arquivo_nota.filename:

            content = await arquivo_nota.read()

            nome = arquivo_nota.filename.lower()

            chave_norm = validar_chave(chave) if chave.strip() else ""



            if nome.endswith(".xml") or content.lstrip().startswith(b"<?xml") or content.lstrip().startswith(b"<"):

                parsed = parse_nfe_xml(content)

                if chave_norm and parsed.chave != chave_norm:

                    raise ValueError("A chave informada não confere com o XML enviado.")

                dest = DATA_DIR / "nfe" / f"{parsed.chave}.xml"

            elif nome.endswith(".pdf") or content[:4] == b"%PDF":

                parsed = parse_nfe_pdf(content, chave_informada=chave_norm)

                if chave_norm and parsed.chave != chave_norm:

                    raise ValueError("A chave informada não confere com o PDF enviado.")

                dest = DATA_DIR / "nfe" / f"{parsed.chave}.pdf"

            else:

                raise ValueError("Envie um arquivo XML ou PDF (DANFE) da nota fiscal.")



            assert_nota_nao_duplicada(db, parsed.chave)

            dest.parent.mkdir(parents=True, exist_ok=True)

            dest.write_bytes(content)

            arquivo_path = str(dest)



        elif chave.strip():

            chave_norm = validar_chave(chave)

            assert_nota_nao_duplicada(db, chave_norm)

            raise ValueError(

                "Para importar pela chave, envie também o arquivo XML ou PDF (DANFE) da nota."

            )

        else:

            raise ValueError("Informe o arquivo XML/PDF ou a chave de acesso da nota.")



        importar_nota_fiscal(db, festejo.id, parsed, arquivo_path)

        detalhe = quote(

            f"NF {parsed.numero}/{parsed.serie} — {parsed.categoria} — {fmt_money(parsed.valor_total)}"

        )

        return RedirectResponse(
            f"/despesas/lancar?toast=success&msg={quote('Importado com sucesso')}&detalhe={detalhe}",
            status_code=303,
        )

    except NotaDuplicadaError as exc:

        return RedirectResponse(
            f"/despesas/lancar?toast=error&msg={quote('Nota não lançada')}&detalhe={quote(str(exc))}",
            status_code=303,
        )

    except ValueError as exc:

        return RedirectResponse(
            f"/despesas/lancar?toast=error&msg={quote(str(exc))}",
            status_code=303,
        )

    except Exception as exc:

        return RedirectResponse(
            f"/despesas/lancar?toast=error&msg={quote(f'Erro ao processar nota: {exc}')}",
            status_code=303,
        )





@app.post("/despesas/manual")

def cadastrar_despesa_manual(

    request: Request,

    emitente_nome: str = Form(...),

    valor: str = Form(...),

    categoria: str = Form(...),

    natureza_operacao: str = Form(""),

    numero: str = Form(""),

    serie: str = Form("1"),

    emitente_cnpj: str = Form(""),

    data_emissao: str = Form(""),

    chave: str = Form(""),

    produtos_resumo: str = Form(""),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    erro = ""

    sucesso = ""



    try:

        valor_num = parse_money(valor)

        data_nota = None

        if data_emissao.strip():

            data_nota = datetime.strptime(data_emissao.strip(), "%Y-%m-%d").date()



        nota = cadastrar_nota_manual(

            db,

            festejo.id,

            emitente_nome=emitente_nome,

            valor_total=valor_num,

            categoria=categoria,

            natureza_operacao=natureza_operacao,

            numero=numero,

            serie=serie,

            emitente_cnpj=emitente_cnpj,

            data_emissao=data_nota,

            chave=chave,

            produtos_resumo=produtos_resumo,

        )

        sucesso = (

            f"Nota manual {nota.numero}/{nota.serie} cadastrada — "

            f"{nota.categoria} — {fmt_money(nota.valor_total)}"

        )

    except NotaDuplicadaError as exc:

        erro = f"Nota não lançada. {exc}"

    except ValueError as exc:

        erro = str(exc)

    except Exception as exc:

        erro = f"Erro ao cadastrar nota: {exc}"



    festejo = get_or_create_festejo_ativo(db)

    return templates.TemplateResponse(
        request,
        "despesas.html",
        _ctx_despesas(db, festejo, "lancar", erro, sucesso),
    )





@app.post("/despesas/{nota_id}/excluir")

def excluir_despesa_nfe(nota_id: int, db: Session = Depends(get_db)):

    try:

        excluir_nota_fiscal(db, nota_id)

    except ValueError:

        pass

    return RedirectResponse("/despesas/lancar", status_code=303)


@app.post("/despesas/{nota_id}/investimento")
def salvar_investimento_despesa(
    nota_id: int,
    investido_em: str = Form(...),
    valor: str = Form(...),
    data: str = Form(""),
    observacao: str = Form(""),
    db: Session = Depends(get_db),
):
    festejo = get_or_create_festejo_ativo(db)
    data_inv = datetime.strptime(data, "%Y-%m-%d").date() if data else None
    valor_num = parse_money(valor)
    existente = (
        db.query(Investimento)
        .filter(Investimento.nota_id == nota_id, Investimento.festejo_id == festejo.id)
        .first()
    )

    try:
        if existente:
            atualizar_investimento(
                db,
                existente.id,
                festejo.id,
                investido_em=investido_em,
                valor=valor_num,
                data_inv=data_inv,
                observacao=observacao,
            )
            msg = "Investimento vinculado à despesa atualizado."
        else:
            criar_investimento(
                db,
                festejo.id,
                investido_em=investido_em,
                valor=valor_num,
                data_inv=data_inv,
                observacao=observacao,
                nota_id=nota_id,
            )
            msg = "Despesa registrada como investimento."
    except ValueError as exc:
        return RedirectResponse(f"/despesas/lancar?erro={quote(str(exc))}", status_code=303)

    return RedirectResponse(f"/despesas/lancar?sucesso={quote(msg)}", status_code=303)


@app.post("/despesas/{nota_id}/editar")

def editar_despesa_nfe(

    request: Request,

    nota_id: int,

    emitente_nome: str = Form(...),

    valor: str = Form(...),

    categoria: str = Form(...),

    natureza_operacao: str = Form(""),

    numero: str = Form(""),

    serie: str = Form("1"),

    emitente_cnpj: str = Form(""),

    data_emissao: str = Form(""),

    produtos_resumo: str = Form(""),

    db: Session = Depends(get_db),

):

    festejo = get_or_create_festejo_ativo(db)

    erro = ""

    sucesso = ""

    try:

        data_nota = None

        if data_emissao.strip():

            data_nota = datetime.strptime(data_emissao.strip(), "%Y-%m-%d").date()

        nota = atualizar_nota_fiscal(

            db,

            nota_id,

            festejo.id,

            emitente_nome=emitente_nome,

            valor_total=parse_money(valor),

            categoria=categoria,

            natureza_operacao=natureza_operacao,

            numero=numero,

            serie=serie,

            emitente_cnpj=emitente_cnpj,

            data_emissao=data_nota,

            produtos_resumo=produtos_resumo,

        )

        sucesso = f"Nota {nota.numero}/{nota.serie} atualizada."

    except ValueError as exc:

        erro = str(exc)

    except Exception as exc:

        erro = f"Erro ao atualizar nota: {exc}"

    return templates.TemplateResponse(
        request,
        "despesas.html",
        _ctx_despesas(db, festejo, "lancar", erro, sucesso),
    )

