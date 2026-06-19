import io
import re
from datetime import datetime

from app.nfe_parser import (
    NFeParsed,
    classificar_categoria,
    parse_chave_nfe,
    validar_chave,
)


def _parse_money(value: str) -> float:
    cleaned = value.replace("R$", "").strip().replace(".", "").replace(",", ".")
    return float(cleaned)


def _parse_br_date(value: str):
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text


def extrair_chave_pdf(text: str) -> str:
    grouped = re.search(
        r"(\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4})",
        text,
    )
    if grouped:
        chave = re.sub(r"\D", "", grouped.group(1))
        if len(chave) == 44:
            return validar_chave(chave)

    compact = re.sub(r"\D", "", text)
    for match in re.finditer(r"[1-9]\d{43}", compact):
        return validar_chave(match.group(0))

    raise ValueError(
        "Chave de acesso (44 dígitos) não encontrada no PDF. "
        "Informe a chave manualmente ou envie o XML da nota."
    )


def extrair_natureza_pdf(text: str) -> str:
    # Layout em colunas: rótulo numa linha, valor na seguinte
    colunas = re.search(
        r"NATUREZA\s+DA\s+OPERA[ÇC][ÃA]O[^\n]*\n\s*(.+)",
        text,
        re.IGNORECASE,
    )
    if colunas:
        linha = colunas.group(1).strip()
        natureza = re.split(r"\s+\d{12,}(?:\s+\d{2}/\d{2}/\d{4})?", linha)[0]
        natureza = re.sub(r"\s+", " ", natureza).strip()
        if len(natureza) > 3:
            return natureza[:255]

    patterns = [
        r"NATUREZA\s+DA\s+OPERA[ÇC][ÃA]O\s*[:\-]?\s*(.+?)(?:\n|PROTOCOLO|INSCRI|FATURA|DUPLICATAS|FOLHA)",
        r"Natureza da Opera[çc][ãa]o\s*[:\-]?\s*(.+?)(?:\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            natureza = re.sub(r"\s+", " ", match.group(1)).strip()
            if len(natureza) > 3:
                return natureza[:255]
    return ""


def extrair_emitente_pdf(text: str) -> tuple[str, str]:
    recebemos = re.search(
        r"RECEBEMOS DE\s+(.+?)\s+OS PRODUTOS(?:/SERVI[ÇC]OS|\s)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if recebemos:
        nome = re.sub(r"\s+", " ", recebemos.group(1)).strip()
        if len(nome) > 3:
            cnpj = _extrair_cnpj(text)
            return nome[:200], cnpj

    bloco = re.search(
        r"IDENTIFICA[ÇC][ÃA]O DO EMITENTE\s*(.+?)(?:DANFE|DESTINAT|REMETENTE|FATURA|PROTOCOLO)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if bloco:
        linhas = [ln.strip() for ln in bloco.group(1).splitlines() if ln.strip()]
        for linha in linhas:
            if re.search(r"CNPJ|CPF|INSCRI|FONE|CEP|RUA|AV\.|AVENIDA", linha, re.I):
                continue
            if len(linha) > 4 and not re.fullmatch(r"[\d./\- ]+", linha):
                cnpj = _extrair_cnpj(bloco.group(1))
                return linha[:200], cnpj

    cnpj = _extrair_cnpj(text)
    if cnpj:
        return f"Emitente CNPJ {cnpj}", cnpj
    return "", ""


def _extrair_cnpj(text: str) -> str:
    match = re.search(r"CNPJ\s*[:/]?\s*([\d./-]{14,18})", text, re.IGNORECASE)
    if match:
        return re.sub(r"\D", "", match.group(1))[:14]
    match = re.search(r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b", text)
    if match:
        return re.sub(r"\D", "", match.group(1))
    return ""


def extrair_numero_serie_pdf(text: str, chave: str) -> tuple[str, str]:
    nro = re.search(r"N[°ºo\.]+\s*([\d.]+)", text, re.IGNORECASE)
    serie = re.search(r"S[ÉE]RIE\s*[:.]?\s*(\d+)", text, re.IGNORECASE)
    info = parse_chave_nfe(chave)
    numero = re.sub(r"\D", "", nro.group(1)).lstrip("0") if nro else info["numero"]
    serie_val = serie.group(1) if serie else info["serie"]
    return numero or info["numero"], serie_val or info["serie"]


def extrair_data_emissao_pdf(text: str, chave: str):
    patterns = [
        r"(?:DATA\s+(?:DE\s+)?EMISS[ÃA]O|EMISS[ÃA]O)\s*(\d{2}/\d{2}/\d{4})",
        r"(\d{2}/\d{2}/\d{4})\s*(?:\d{2}:\d{2}:\d{2})?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data = _parse_br_date(match.group(1))
            if data:
                return data
    return parse_chave_nfe(chave)["data_emissao"]


def _valores_monetarios_linha(linha: str) -> list[str]:
    return re.findall(r"\d[\d.,]*", linha)


def _valor_ultimo_campo_linha_seguinte(text: str, marcador: str) -> float | None:
    """DANFE em colunas: rótulo numa linha e valores monetários na linha seguinte."""
    match = re.search(marcador, text, re.IGNORECASE)
    if not match:
        return None
    proxima = re.search(r"\n[ \t]*([^\n]+)", text[match.end() :])
    if not proxima:
        return None
    valores = _valores_monetarios_linha(proxima.group(1))
    if not valores:
        return None
    return round(_parse_money(valores[-1]), 2)


def extrair_valor_total_pdf(text: str) -> float:
    # Canhoto / cabeçalho do DANFE (ex.: "Valor Total: 313,85 NF-e")
    cabecalho = re.search(r"Valor\s+Total\s*:\s*([\d.,]+)", text, re.IGNORECASE)
    if cabecalho:
        valor = round(_parse_money(cabecalho.group(1)), 2)
        if valor > 0:
            return valor

    # Valor na mesma linha do rótulo — [ \t] evita atravessar quebra de linha com \s
    inline_patterns = [
        r"VALOR\s+TOTAL\s+DA\s+NOTA[ \t]*(?:R\$)?[ \t]*([\d.,]+)",
        r"VALOR\s+TOTAL\s+NOTA[ \t]*(?:R\$)?[ \t]*([\d.,]+)",
        r"V\.?\s*TOTAL\s+DA\s+NOTA[ \t]*(?:R\$)?[ \t]*([\d.,]+)",
        r"Valor\s+Total\s+(?:da\s+Nota)?[ \t]*(?:R\$)?[ \t]*([\d.,]+)",
    ]
    for pattern in inline_patterns:
        for raw in reversed(re.findall(pattern, text, re.IGNORECASE)):
            valor = round(_parse_money(raw), 2)
            if valor > 0:
                return valor

    # Bloco "Cálculo do imposto": último valor da linha após o rótulo
    for marcador in (
        r"VALOR\s+TOTAL\s+DA\s+NOTA",
        r"VALOR\s+TOTAL\s+DOS\s+PRODUTOS",
    ):
        valor = _valor_ultimo_campo_linha_seguinte(text, marcador)
        if valor and valor > 0:
            return valor

    raise ValueError(
        "Valor total da nota não encontrado no PDF. "
        "Verifique se o arquivo é um DANFE legível (não escaneado como imagem)."
    )


def extrair_produtos_pdf(text: str) -> tuple[list[str], list[str]]:
    produtos: list[str] = []
    cfops: list[str] = []

    for match in re.finditer(
        r"^\s*\d+\s+(.+?)\s+(\d{8})\s+(\d{3,4})\s+(\d{4})\s",
        text,
        re.MULTILINE,
    ):
        descricao = re.sub(r"\s+", " ", match.group(1)).strip()
        cfop = match.group(4)
        if descricao and len(descricao) > 2:
            produtos.append(descricao)
            cfops.append(cfop)

    if not produtos:
        secao = re.search(
            r"DESCRI[ÇC][ÃA]O DO PRODUTO(?:/SERVI[ÇC]O)?\s*(.+?)(?:DADOS ADICIONAIS|INFORMA[ÇC][ÕO]ES COMPLEMENTARES|RESERVADO)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if secao:
            for linha in secao.group(1).splitlines():
                linha = linha.strip()
                if len(linha) > 5 and not linha.lower().startswith(("código", "codigo", "ncm")):
                    produtos.append(linha[:120])

    return produtos, cfops


def parse_nfe_pdf_text(text: str, chave_informada: str = "") -> NFeParsed:
    text = _normalize_text(text)
    if len(text.strip()) < 80:
        raise ValueError(
            "O PDF não contém texto extraível. "
            "Envie o XML ou um PDF gerado eletronicamente (DANFE), não uma foto escaneada."
        )

    chave = validar_chave(chave_informada) if chave_informada.strip() else extrair_chave_pdf(text)
    emitente_nome, emitente_cnpj = extrair_emitente_pdf(text)
    natureza = extrair_natureza_pdf(text) or "Operação registrada via DANFE (PDF)"
    numero, serie = extrair_numero_serie_pdf(text, chave)
    data_emissao = extrair_data_emissao_pdf(text, chave)
    valor_total = extrair_valor_total_pdf(text)
    produtos, cfops = extrair_produtos_pdf(text)
    categoria = classificar_categoria(natureza, produtos, cfops)

    resumo = "; ".join(produtos[:3])
    if len(produtos) > 3:
        resumo += f" (+{len(produtos) - 3} itens)"

    info = parse_chave_nfe(chave)
    return NFeParsed(
        chave=chave,
        numero=numero,
        serie=serie,
        modelo=info["modelo"],
        emitente_nome=emitente_nome,
        emitente_cnpj=emitente_cnpj or info["cnpj"],
        data_emissao=data_emissao,
        natureza_operacao=natureza,
        valor_total=valor_total,
        categoria=categoria,
        produtos_resumo=resumo,
        cfop_principal=cfops[0] if cfops else "",
        completa=True,
    )


def parse_nfe_pdf(content: bytes, chave_informada: str = "") -> NFeParsed:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        pages_text = [page.extract_text() or "" for page in pdf.pages]
    text = "\n".join(pages_text)
    return parse_nfe_pdf_text(text, chave_informada=chave_informada)


def parse_nfe_pdf_file(path: str, chave_informada: str = "") -> NFeParsed:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return parse_nfe_pdf_text(text, chave_informada=chave_informada)
