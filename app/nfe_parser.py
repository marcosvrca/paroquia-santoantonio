import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class NFeParsed:
    chave: str
    numero: str
    serie: str
    modelo: str
    emitente_nome: str
    emitente_cnpj: str
    data_emissao: date | None
    natureza_operacao: str
    valor_total: float
    categoria: str
    produtos_resumo: str = ""
    cfop_principal: str = ""
    completa: bool = True


CATEGORIAS_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Alimentação", ["aliment", "comida", "bebida", "carne", "frango", "arroz", "feij", "açou", "acou", "padaria", "latic", "horti", "gelo", "refriger", "suco", "cerveja", "pao", "pão"]),
    ("Limpeza e higiene", ["limpeza", "detergente", "sabao", "sabão", "desinfet", "higiene", "lixeira", "vassoura", "papel hig"]),
    ("Construção e estrutura", ["constru", "cimento", "tinta", "madeira", "locacao", "locação", "lona", "tenda", "estrutura", "aluguel", "andaime", "muro", "pintura"]),
    ("Som e iluminação", ["som", "audio", "áudio", "ilumin", "luz", "led", "microfone", "caixa acust"]),
    ("Material elétrico", ["eletric", "elétric", "fio", "tomada", "disjuntor", "lampada", "lâmpada", "extensao", "extensão"]),
    ("Combustível e transporte", ["combust", "gasolina", "diesel", "etanol", "frete", "transport", "combustivel", "combustível"]),
    ("Gás", ["gás", "gas ", "botijao", "botijão", "glp", "permuta"]),
    ("Descartáveis", ["descart", "copo", "prato", "talher", "guardanapo", "embalag", "sacola plast"]),
    ("Serviços", ["servico", "serviço", "prestacao", "prestação", "mao de obra", "mão de obra", "honorario", "honorário", "vigia", "seguranca", "segurança", "guarda"]),
    ("Lembraças e convites", ["lembranc", "lembrança", "convite", "brinde", "personaliz"]),
]


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(parent: ET.Element | None, name: str) -> str:
    if parent is None:
        return ""
    for child in parent:
        if _local(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    value = value.strip()
    try:
        if "T" in value:
            return datetime.fromisoformat(value[:19]).date()
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def normalizar_chave(chave: str) -> str:
    return re.sub(r"\D", "", chave or "")


def validar_chave(chave: str) -> str:
    chave = normalizar_chave(chave)
    if len(chave) != 44:
        raise ValueError("A chave de acesso deve ter 44 dígitos.")
    return chave


def parse_chave_nfe(chave: str) -> dict:
    chave = validar_chave(chave)
    aamm = chave[2:6]
    try:
        ano = 2000 + int(aamm[0:2])
        mes = int(aamm[2:4])
        data_ref = date(ano, mes, 1)
    except ValueError:
        data_ref = None

    return {
        "chave": chave,
        "cnpj": chave[6:20],
        "modelo": chave[20:22],
        "serie": str(int(chave[22:25])),
        "numero": str(int(chave[25:34])),
        "data_emissao": data_ref,
    }


def classificar_categoria(natureza: str, produtos: list[str], cfops: list[str]) -> str:
    texto = " ".join([natureza, *produtos, *cfops]).lower()
    for categoria, palavras in CATEGORIAS_KEYWORDS:
        if any(p in texto for p in palavras):
            return categoria
    return "Despesas gerais"


def parse_nfe_xml(content: str | bytes) -> NFeParsed:
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="ignore")
    content = content.strip()
    if content.startswith("\ufeff"):
        content = content[1:]

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("Arquivo XML inválido ou corrompido.") from exc

    inf = None
    for el in root.iter():
        if _local(el.tag) == "infNFe":
            inf = el
            break
    if inf is None:
        raise ValueError("XML não contém uma NF-e válida (infNFe não encontrado).")

    chave = ""
    if inf.get("Id"):
        chave = inf.get("Id", "").replace("NFe", "")
    if not chave or len(chave) != 44:
        chave_el = None
        for el in root.iter():
            if _local(el.tag) == "chNFe" and el.text:
                chave_el = el.text.strip()
                break
        chave = validar_chave(chave_el or chave)

    ide = emit = total = None
    for child in inf:
        tag = _local(child.tag)
        if tag == "ide":
            ide = child
        elif tag == "emit":
            emit = child
        elif tag == "total":
            total = child

    icms_tot = None
    if total is not None:
        for child in total:
            if _local(child.tag) == "ICMSTot":
                icms_tot = child
                break

    produtos: list[str] = []
    cfops: list[str] = []
    for el in inf.iter():
        if _local(el.tag) == "det":
            prod = None
            for child in el:
                if _local(child.tag) == "prod":
                    prod = child
                    break
            if prod is not None:
                nome = _text(prod, "xProd")
                cfop = _text(prod, "CFOP")
                if nome:
                    produtos.append(nome)
                if cfop:
                    cfops.append(cfop)

    natureza = _text(ide, "natOp")
    numero = _text(ide, "nNF") or parse_chave_nfe(chave)["numero"]
    serie = _text(ide, "serie") or parse_chave_nfe(chave)["serie"]
    modelo = _text(ide, "mod") or parse_chave_nfe(chave)["modelo"]
    data_emissao = _parse_date(_text(ide, "dhEmi") or _text(ide, "dEmi"))
    emitente = _text(emit, "xNome")
    cnpj = _text(emit, "CNPJ") or _text(emit, "CPF") or parse_chave_nfe(chave)["cnpj"]

    valor_txt = _text(icms_tot, "vNF") if icms_tot is not None else "0"
    valor_total = float(valor_txt.replace(",", ".")) if valor_txt else 0.0

    categoria = classificar_categoria(natureza, produtos, cfops)
    resumo = "; ".join(produtos[:3])
    if len(produtos) > 3:
        resumo += f" (+{len(produtos) - 3} itens)"

    return NFeParsed(
        chave=chave,
        numero=numero,
        serie=serie,
        modelo=modelo,
        emitente_nome=emitente,
        emitente_cnpj=cnpj,
        data_emissao=data_emissao,
        natureza_operacao=natureza,
        valor_total=round(valor_total, 2),
        categoria=categoria,
        produtos_resumo=resumo,
        cfop_principal=cfops[0] if cfops else "",
        completa=True,
    )


def parse_por_chave(chave: str) -> NFeParsed:
    info = parse_chave_nfe(chave)
    return NFeParsed(
        chave=info["chave"],
        numero=info["numero"],
        serie=info["serie"],
        modelo=info["modelo"],
        emitente_nome=f"CNPJ {info['cnpj']}",
        emitente_cnpj=info["cnpj"],
        data_emissao=info["data_emissao"],
        natureza_operacao="Importada apenas pela chave — envie o XML para completar",
        valor_total=0.0,
        categoria="Despesas gerais",
        completa=False,
    )
