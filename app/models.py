from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

FORMAS_PAGAMENTO = [
    {"campo": "dinheiro", "label": "Dinheiro"},
    {"campo": "debito", "label": "Cartão débito"},
    {"campo": "credito", "label": "Cartão crédito"},
    {"campo": "pix", "label": "Pix"},
]


class Festejo(Base):
    __tablename__ = "festejos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    ano: Mapped[int] = mapped_column(Integer, nullable=False)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    ativo: Mapped[bool] = mapped_column(default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    dias: Mapped[list["DiaFestejo"]] = relationship(back_populates="festejo", cascade="all, delete-orphan")
    despesas: Mapped[list["LancamentoFinanceiro"]] = relationship(
        back_populates="festejo", cascade="all, delete-orphan"
    )
    notas_fiscais: Mapped[list["NotaFiscal"]] = relationship(
        back_populates="festejo", cascade="all, delete-orphan"
    )
    patrocinio_movimentos: Mapped[list["PatrocinioMovimento"]] = relationship(
        back_populates="festejo", cascade="all, delete-orphan"
    )
    investimentos: Mapped[list["Investimento"]] = relationship(
        back_populates="festejo", cascade="all, delete-orphan"
    )


class DiaFestejo(Base):
    __tablename__ = "dias_festejo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    festejo_id: Mapped[int] = mapped_column(ForeignKey("festejos.id"), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    numero_dia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rotulo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    festejo: Mapped["Festejo"] = relationship(back_populates="dias")
    relatorio_pdf: Mapped["RelatorioPdf | None"] = relationship(
        back_populates="dia", uselist=False, cascade="all, delete-orphan"
    )
    caixa: Mapped["CaixaRegistro | None"] = relationship(
        back_populates="dia", uselist=False, cascade="all, delete-orphan"
    )
    leilao_movimentos: Mapped[list["LeilaoMovimento"]] = relationship(
        back_populates="dia", cascade="all, delete-orphan"
    )
    rifa_movimentos: Mapped[list["RifaMovimento"]] = relationship(
        back_populates="dia", cascade="all, delete-orphan"
    )
    sangrias: Mapped[list["Sangria"]] = relationship(back_populates="dia", cascade="all, delete-orphan")


class RelatorioPdf(Base):
    __tablename__ = "relatorios_pdf"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dia_id: Mapped[int | None] = mapped_column(ForeignKey("dias_festejo.id"), nullable=True)
    festejo_id: Mapped[int] = mapped_column(ForeignKey("festejos.id"), nullable=False)
    arquivo_nome: Mapped[str] = mapped_column(String(255), nullable=False)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    eh_acumulado: Mapped[bool] = mapped_column(default=False)
    dinheiro: Mapped[float] = mapped_column(Float, default=0)
    credito: Mapped[float] = mapped_column(Float, default=0)
    debito: Mapped[float] = mapped_column(Float, default=0)
    pix: Mapped[float] = mapped_column(Float, default=0)
    total_vendas: Mapped[float] = mapped_column(Float, default=0)
    total_gratuidade: Mapped[float] = mapped_column(Float, default=0)
    total_geral: Mapped[float] = mapped_column(Float, default=0)
    importado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    dia: Mapped["DiaFestejo | None"] = relationship(back_populates="relatorio_pdf")
    produtos: Mapped[list["ProdutoVenda"]] = relationship(
        back_populates="relatorio", cascade="all, delete-orphan"
    )


class ProdutoVenda(Base):
    __tablename__ = "produtos_venda"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_pdf.id"), nullable=False)
    secao: Mapped[str] = mapped_column(String(20), default="vendas")
    codigo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    produto: Mapped[str] = mapped_column(String(200), nullable=False)
    quantidade: Mapped[float] = mapped_column(Float, default=0)
    valor_unitario: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)

    relatorio: Mapped["RelatorioPdf"] = relationship(back_populates="produtos")


class CaixaRegistro(Base):
    __tablename__ = "caixas_registro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dia_id: Mapped[int] = mapped_column(ForeignKey("dias_festejo.id"), unique=True, nullable=False)
    caixa_numero: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    troco: Mapped[float] = mapped_column(Float, default=0)
    dinheiro: Mapped[float] = mapped_column(Float, default=0)
    debito: Mapped[float] = mapped_column(Float, default=0)
    credito: Mapped[float] = mapped_column(Float, default=0)
    pix: Mapped[float] = mapped_column(Float, default=0)
    leilao_pago_caixa: Mapped[float] = mapped_column(Float, default=0)

    dia: Mapped["DiaFestejo"] = relationship(back_populates="caixa")


class LeilaoMovimento(Base):
    __tablename__ = "leilao_movimentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dia_id: Mapped[int] = mapped_column(ForeignKey("dias_festejo.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    descricao: Mapped[str] = mapped_column(String(255), default="")
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    dia: Mapped["DiaFestejo"] = relationship(back_populates="leilao_movimentos")


class RifaMovimento(Base):
    __tablename__ = "rifa_movimentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dia_id: Mapped[int | None] = mapped_column(ForeignKey("dias_festejo.id"), nullable=True)
    festejo_id: Mapped[int] = mapped_column(ForeignKey("festejos.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    categoria: Mapped[str] = mapped_column(String(30), default="outro")
    vendedor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    descricao: Mapped[str] = mapped_column(String(255), default="")
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)

    dia: Mapped["DiaFestejo | None"] = relationship(back_populates="rifa_movimentos")


class PatrocinioMovimento(Base):
    __tablename__ = "patrocinio_movimentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    festejo_id: Mapped[int] = mapped_column(ForeignKey("festejos.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    patrocinador: Mapped[str | None] = mapped_column(String(120), nullable=True)
    descricao: Mapped[str] = mapped_column(String(255), default="")
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)

    festejo: Mapped["Festejo"] = relationship(back_populates="patrocinio_movimentos")


class Investimento(Base):
    __tablename__ = "investimentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    festejo_id: Mapped[int] = mapped_column(ForeignKey("festejos.id"), nullable=False)
    nota_id: Mapped[int | None] = mapped_column(ForeignKey("notas_fiscais.id"), nullable=True, unique=True)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    investido_em: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    festejo: Mapped["Festejo"] = relationship(back_populates="investimentos")
    nota_fiscal: Mapped["NotaFiscal | None"] = relationship(back_populates="investimento", uselist=False)


class Sangria(Base):
    __tablename__ = "sangrias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dia_id: Mapped[int] = mapped_column(ForeignKey("dias_festejo.id"), nullable=False)
    destino: Mapped[str] = mapped_column(String(255), default="")
    valor: Mapped[float] = mapped_column(Float, nullable=False)

    dia: Mapped["DiaFestejo"] = relationship(back_populates="sangrias")


class LancamentoFinanceiro(Base):
    __tablename__ = "lancamentos_financeiros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    festejo_id: Mapped[int] = mapped_column(ForeignKey("festejos.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    categoria: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str] = mapped_column(String(255), default="")
    valor: Mapped[float] = mapped_column(Float, nullable=False)

    festejo: Mapped["Festejo"] = relationship(back_populates="despesas")
    nota_fiscal: Mapped["NotaFiscal | None"] = relationship(back_populates="lancamento", uselist=False)


class NotaFiscal(Base):
    __tablename__ = "notas_fiscais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    festejo_id: Mapped[int] = mapped_column(ForeignKey("festejos.id"), nullable=False)
    lancamento_id: Mapped[int | None] = mapped_column(ForeignKey("lancamentos_financeiros.id"), nullable=True)
    chave: Mapped[str] = mapped_column(String(44), unique=True, nullable=False)
    numero: Mapped[str] = mapped_column(String(20), default="")
    serie: Mapped[str] = mapped_column(String(10), default="")
    modelo: Mapped[str] = mapped_column(String(5), default="55")
    emitente_nome: Mapped[str] = mapped_column(String(200), default="")
    emitente_cnpj: Mapped[str] = mapped_column(String(20), default="")
    data_emissao: Mapped[date | None] = mapped_column(Date, nullable=True)
    natureza_operacao: Mapped[str] = mapped_column(String(255), default="")
    categoria: Mapped[str] = mapped_column(String(120), default="Despesas gerais")
    valor_total: Mapped[float] = mapped_column(Float, default=0)
    produtos_resumo: Mapped[str] = mapped_column(String(500), default="")
    cfop_principal: Mapped[str] = mapped_column(String(10), default="")
    xml_arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completa: Mapped[bool] = mapped_column(default=True)
    importado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    festejo: Mapped["Festejo"] = relationship(back_populates="notas_fiscais")
    lancamento: Mapped["LancamentoFinanceiro | None"] = relationship(back_populates="nota_fiscal")
    investimento: Mapped["Investimento | None"] = relationship(
        back_populates="nota_fiscal", uselist=False, cascade="all, delete-orphan"
    )
