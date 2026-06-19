import re
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class ProdutoItem:
    codigo: int | None
    produto: str
    quantidade: float
    valor_unitario: float
    total: float
    secao: str = "vendas"


@dataclass
class RelatorioVendas:
    data_inicio: date | None = None
    data_fim: date | None = None
    eh_acumulado: bool = False
    dinheiro: float = 0
    credito: float = 0
    debito: float = 0
    pix: float = 0
    total_vendas: float = 0
    total_gratuidade: float = 0
    total_geral: float = 0
    produtos: list[ProdutoItem] = field(default_factory=list)


def parse_money(value: str) -> float:
    cleaned = value.replace("R$", "").strip().replace(".", "").replace(",", ".")
    return float(cleaned)


def parse_br_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%d/%m/%Y").date()


def parse_relatorio_vendas(text: str) -> RelatorioVendas:
    relatorio = RelatorioVendas()

    filtro = re.search(
        r"Filtro por Data:\s*(\d{2}/\d{2}/\d{4})\s*a\s*(\d{2}/\d{2}/\d{4})",
        text,
        re.IGNORECASE,
    )
    if filtro:
        relatorio.data_inicio = parse_br_date(filtro.group(1))
        relatorio.data_fim = parse_br_date(filtro.group(2))
        relatorio.eh_acumulado = relatorio.data_inicio != relatorio.data_fim

    pagamentos = re.search(
        r"Dinheiro:\s*R\$\s*([\d.,]+)\s*Cr[eé]dito:\s*R\$\s*([\d.,]+)\s*D[eé]bito:\s*R\$\s*([\d.,]+)\s*Pix:\s*R\$\s*([\d.,]+)",
        text,
        re.IGNORECASE,
    )
    if pagamentos:
        relatorio.dinheiro = parse_money(pagamentos.group(1))
        relatorio.credito = parse_money(pagamentos.group(2))
        relatorio.debito = parse_money(pagamentos.group(3))
        relatorio.pix = parse_money(pagamentos.group(4))

    total_vendas = re.search(r"Total de VENDAS\s*R\$\s*([\d.,]+)", text, re.IGNORECASE)
    if total_vendas:
        relatorio.total_vendas = parse_money(total_vendas.group(1))

    total_grat = re.search(r"Total de GRATUIDADE\s*R\$\s*([\d.,]+)", text, re.IGNORECASE)
    if total_grat:
        relatorio.total_gratuidade = parse_money(total_grat.group(1))

    total_geral = re.search(r"Total GERAL\s*R\$\s*([\d.,]+)", text, re.IGNORECASE)
    if total_geral:
        relatorio.total_geral = parse_money(total_geral.group(1))

    secao_atual = "vendas"
    linha_produto = re.compile(
        r"^(\d+)\s+(.+?)\s+([\d.,]+)\s+R\$\s*([\d.,]+)\s+R\$\s*([\d.,]+)\s*$"
    )

    for linha in text.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.lower() == "gratuidade":
            secao_atual = "gratuidade"
            continue
        if linha.lower().startswith("código") or linha.lower().startswith("codigo"):
            continue
        if linha.lower() == "vendas":
            secao_atual = "vendas"
            continue

        match = linha_produto.match(linha)
        if match:
            relatorio.produtos.append(
                ProdutoItem(
                    codigo=int(match.group(1)),
                    produto=match.group(2).strip(),
                    quantidade=parse_money(match.group(3)),
                    valor_unitario=parse_money(match.group(4)),
                    total=parse_money(match.group(5)),
                    secao=secao_atual,
                )
            )

    return relatorio


def parse_pdf_file(path: str) -> RelatorioVendas:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return parse_relatorio_vendas(text)
