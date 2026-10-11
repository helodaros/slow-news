"""Gera docs/index.html do Slow News a partir dos feeds RSS dos portais."""

import concurrent.futures as cf
import html
import json
import math
import re
import sys
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import feedparser

RAIZ = Path(__file__).parent
BRT = timezone(timedelta(hours=-3))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
POR_EDITORIA = 10
MAX_POR_FONTE = 2
MIN_RESUMO = 160

EDITORIAS = [
    ("brasil", "Brasil", "#008a2e"),
    ("politica", "Política", "#00339a"),
    ("mundo", "Mundo", "#c40000"),
    ("cultura", "Cultura", "#8a2c8a"),
    ("economia", "Economia", "#e65c00"),
    ("tecnologia", "Tecnologia", "#007fa8"),
]

# Linha editorial usada para alternar as fontes em cada editoria.
FONTES = {
    "g1": {"nome": "g1", "site": "g1.globo.com", "linha": "centro", "feeds": [
        ("https://g1.globo.com/rss/g1/", None),
        ("https://g1.globo.com/rss/g1/politica/", "politica")]},
    "uol": {"nome": "UOL", "site": "uol.com.br", "linha": "centro", "feeds": [
        ("https://rss.uol.com.br/feed/noticias.xml", None),
        ("https://rss.uol.com.br/feed/economia.xml", "economia"),
        ("https://rss.uol.com.br/feed/tecnologia.xml", "tecnologia")]},
    "terra": {"nome": "Terra", "site": "terra.com.br", "linha": "centro", "feeds": [
        ("https://www.terra.com.br/rss.xml", None)]},
    "folha": {"nome": "Folha de S.Paulo", "site": "folha.uol.com.br", "linha": "centro", "feeds": [
        ("https://feeds.folha.uol.com.br/emcimadahora/rss091.xml", None),
        ("https://feeds.folha.uol.com.br/poder/rss091.xml", "politica"),
        ("https://feeds.folha.uol.com.br/mundo/rss091.xml", "mundo"),
        ("https://feeds.folha.uol.com.br/mercado/rss091.xml", "economia"),
        ("https://feeds.folha.uol.com.br/cotidiano/rss091.xml", "brasil"),
        ("https://feeds.folha.uol.com.br/ilustrada/rss091.xml", "cultura"),
        ("https://feeds.folha.uol.com.br/tec/rss091.xml", "tecnologia")]},
    "valor": {"nome": "Valor Econômico", "site": "valor.globo.com", "linha": "centro", "feeds": [
        ("https://pox.globo.com/rss/valor/", "economia")]},
    "poder360": {"nome": "Poder360", "site": "poder360.com.br", "linha": "centro", "feeds": [
        ("https://www.poder360.com.br/feed/", None)]},
    "estadao": {"nome": "Estadão", "site": "estadao.com.br", "linha": "centro-direita", "feeds": [
        ("https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/politica/", "politica"),
        ("https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/brasil/", "brasil"),
        ("https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/internacional/", "mundo"),
        ("https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/economia/", "economia"),
        ("https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/cultura/", "cultura")]},
    "cnn": {"nome": "CNN Brasil", "site": "cnnbrasil.com.br", "linha": "centro-direita", "feeds": [
        ("https://www.cnnbrasil.com.br/feed/", None)]},
    "metropoles": {"nome": "Metrópoles", "site": "metropoles.com", "linha": "centro-direita", "feeds": [
        ("https://www.metropoles.com/feed", None),
        ("https://www.metropoles.com/brasil/feed", "brasil"),
        ("https://www.metropoles.com/mundo/feed", "mundo")]},
    "infomoney": {"nome": "InfoMoney", "site": "infomoney.com.br", "linha": "centro-direita", "feeds": [
        ("https://www.infomoney.com.br/feed/", None)]},
    "brasil247": {"nome": "Brasil 247", "site": "brasil247.com", "linha": "esquerda", "feeds": [
        ("https://www.brasil247.com/feed", None)]},
    "brasildefato": {"nome": "Brasil de Fato", "site": "brasildefato.com.br", "linha": "esquerda", "feeds": [
        ("https://www.brasildefato.com.br/feed/", None)]},
    "cartacapital": {"nome": "CartaCapital", "site": "cartacapital.com.br", "linha": "esquerda", "feeds": [
        ("https://www.cartacapital.com.br/feed/", None),
        ("https://www.cartacapital.com.br/politica/feed/", "politica"),
        ("https://www.cartacapital.com.br/mundo/feed/", "mundo"),
        ("https://www.cartacapital.com.br/economia/feed/", "economia"),
        ("https://www.cartacapital.com.br/cultura/feed/", "cultura"),
        ("https://www.cartacapital.com.br/tecnologia/feed/", "tecnologia")]},
    "dcm": {"nome": "Diário do Centro do Mundo", "site": "diariodocentrodomundo.com.br", "linha": "esquerda", "feeds": [
        ("https://www.diariodocentrodomundo.com.br/feed/", None)]},
    "diplomatique": {"nome": "Le Monde Diplomatique Brasil", "site": "diplomatique.org.br", "linha": "esquerda", "feeds": [
        ("https://diplomatique.org.br/feed/", None)]},
}

SEGMENTOS = {
    "politica": {"politica", "poder", "eleicoes", "eleicoes-2026", "governo", "congresso", "politica-brasil"},
    "mundo": {"mundo", "internacional", "world", "america-latina"},
    "economia": {"economia", "mercado", "mercados", "negocios", "empresas", "financas", "agronegocios",
                 "money", "macroeconomia", "investimentos", "minhas-financas", "carreira"},
    "tecnologia": {"tecnologia", "tec", "tilt", "link", "byte", "inovacao", "ciencia-e-tecnologia", "inteligencia-artificial"},
    "cultura": {"cultura", "ilustrada", "pop-arte", "entretenimento", "cinema", "musica", "livros", "literatura",
                "artes", "teatro", "exposicoes", "diversao", "pop", "series", "filmes"},
    "brasil": {"brasil", "cotidiano", "nacional", "saude", "educacao", "meio-ambiente", "ciencia", "sustentabilidade",
               "seguranca", "clima"},
}
REGIONAIS = {"sudeste", "nordeste", "sul", "norte", "centro-oeste", "distrito-federal", "sao-paulo", "minas-gerais",
             "rio-de-janeiro", "parana", "bahia", "pernambuco", "goias", "ceara", "rio-grande-do-sul", "regional"}
UFS = {"ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms", "mg", "pa", "pb", "pr", "pe", "pi",
       "rj", "rn", "rs", "ro", "rr", "sc", "sp", "se", "to"}
EXCLUIR_SEGMENTOS = {"esporte", "esportes", "futebol", "celebridades", "famosos", "gente", "horoscopo", "loterias",
                     "bbb", "reality", "blog", "blogs", "opiniao", "colunas", "coluna", "colunistas", "podcast",
                     "podcasts", "video", "videos", "patrocinado", "publieditorial", "brasileirao", "receitas",
                     "fotos", "galerias", "loteria", "astrologia", "tv-e-famosos", "vida-e-estilo", "bem-estar",
                     "curiosidades", "viagem", "turismo", "moda", "beleza", "pets"}
EXCLUIR_TAGS = {"esportes", "esporte", "celebridades", "futebol", "brasileirão", "horóscopo", "bbb", "famosos",
                "loterias", "fofoca", "reality show", "patrocinado", "blog", "opinião"}
EXCLUIR_TITULO = re.compile(
    r"\b(bbb|big brother|a fazenda|reality|namorad[oa]|ex-marido|ex-mulher|influenciador[a]?|"
    r"mega-sena|lotofácil|quina|horóscopo|signo|onde assistir|palpite|relacionamento|reconcilia\w*|separação|"
    r"casamento|affair|\d+ dicas|dicas para|receita)\b", re.I)

TAGS = {
    "politica": ("política", "poder", "eleições", "eleicoes", "congresso", "stf", "governo lula"),
    "mundo": ("mundo", "internacional"),
    "economia": ("economia", "mercados", "macroeconomia", "negócios", "finanças", "investimentos"),
    "tecnologia": ("tecnologia", "inteligência artificial", "inovação"),
    "cultura": ("cultura", "cinema", "música", "livros", "literatura", "artes", "teatro", "exposição"),
    "brasil": ("brasil", "nacional", "saúde", "educação", "meio ambiente", "segurança pública"),
}

PALAVRAS = {
    "politica": r"\b(lula|bolsonaro|flávio|tarcísio|stf|tse|congresso|senado|câmara|deputad\w*|senador\w*|ministr\w*|"
                r"eleiç\w*|eleitor\w*|candidat\w*|campanha|governador\w*|planalto|pec|janones|moraes)\b",
    "economia": r"\b(dólar|ibovespa|bolsa|juros|selic|inflação|ipca|pib|petrobras|copom|tesouro|imposto\w*|"
                r"arrecadação|mercado|banco central|fiscal)\b",
    "tecnologia": r"\b(inteligência artificial|ia|chatgpt|openai|nvidia|microsoft|big techs?|iphone|software|"
                  r"startups?|semicondutor\w*|ciberataque|hacker\w*)\b",
    "mundo": r"\b(eua|estados unidos|trump|china|rússia|ucrânia|israel|gaza|irã|europa|argentina|milei|venezuela|"
             r"otan|onu|papa)\b",
}
PALAVRAS = {k: re.compile(v, re.I) for k, v in PALAVRAS.items()}

STOPWORDS = set("""a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para pra
com sem sob sobre e ou que se ao aos à às é ser foi são diz afirma após apos contra mais menos como entre até ate
já ja não nao sim seu sua seus suas ele ela eles elas isso este esta esse essa quem onde quando vai pode deve
neste nesta desta deste diz dizem veja saiba entenda""".split())


def baixar(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


TAGS_EM_LINHA = re.compile(r"</?(a|b|i|em|strong|span|abbr|sup|sub|u|small|mark|cite|q|font)\b[^>]*>", re.I)


def limpar(texto):
    texto = TAGS_EM_LINHA.sub("", texto or "")
    texto = html.unescape(re.sub(r"<[^>]+>", " ", texto))
    texto = re.sub(r"(O post|The post)\s.*?(apareceu primeiro em|appeared first on)\s.*$", "", texto, flags=re.S)
    texto = re.sub(r"\s*(Leia mais|Continue lendo|Leia também)\b.*$", "", texto, flags=re.S | re.I)
    texto = re.sub(r"\s*\[(…|\.\.\.)\].*$", "…", texto, flags=re.S)
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = re.sub(r"\s+([,.;:!?)\]])", r"\1", texto)
    return re.sub(r"([(\[])\s+", r"\1", texto)


def cortar(texto, limite=460):
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0].rstrip(",;:.-–— ")
    return corte + "…"


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def fonte_do_link(link, fonte_feed):
    host = urlparse(link).netloc.lower()
    for chave, f in FONTES.items():
        if chave != "uol" and host.endswith(f["site"]):
            return chave
    if host.endswith("uol.com.br"):
        return "uol"
    return fonte_feed


def classificar(link, titulo, tags, padrao):
    segs = [s for s in urlparse(link).path.lower().split("/") if s]
    tags_l = {t.lower().strip() for t in tags}
    if set(segs) & EXCLUIR_SEGMENTOS or tags_l & EXCLUIR_TAGS or EXCLUIR_TITULO.search(titulo):
        return None, False, 0
    regional = bool(segs) and (segs[0] in UFS or segs[0] in REGIONAIS) or "tnonline" in link

    cat, peso = None, 3
    if any(seg in SEGMENTOS["tecnologia"] for seg in segs[:4]):
        cat = "tecnologia"
    for seg in segs[:3]:
        if cat:
            break
        cat = "politica" if seg.startswith("poder-") else next((c for c, conj in SEGMENTOS.items() if seg in conj), None)
    if not cat:
        peso = 2
        cat = next((c for c, termos in TAGS.items() if any(t.startswith(termos) for t in tags_l)), None) or padrao
    if not cat:
        peso = 1
        cat = next((c for c, rx in PALAVRAS.items() if rx.search(titulo)), None)
    if not cat:
        return None, False, 0
    if cat == "brasil" and PALAVRAS["politica"].search(titulo):
        cat = "politica"
    return cat, regional, peso


def ler_feed(chave, url, padrao):
    try:
        dados = baixar(url)
        if b"encoding=" not in dados[:200]:
            for cod in ("utf-8", "cp1252", "latin-1"):
                try:
                    dados = dados.decode(cod)
                    break
                except UnicodeDecodeError:
                    pass
        feed = feedparser.parse(dados)
    except Exception as e:
        print(f"  ! falhou {url}: {e}", file=sys.stderr)
        return []
    itens = []
    for e in feed.entries:
        link, titulo = e.get("link", "").strip(), limpar(e.get("title", ""))
        link = re.sub(r"^https?://redir\.[^*]+\*", "", link)
        if not link.startswith(("https://", "http://")) or not titulo:
            continue
        data = e.get("published_parsed") or e.get("updated_parsed")
        quando = datetime(*data[:6], tzinfo=timezone.utc) if data else None
        tags = [t.get("term", "") for t in e.get("tags", [])]
        cat, regional, peso = classificar(link, titulo, tags, padrao)
        if not cat:
            continue
        bruto = e.get("summary", "")
        if "glbimg.com" in bruto[:300]:
            # g1 e Valor abrem o resumo com a foto, a legenda e às vezes o crédito (linha curta sem ponto).
            bruto = re.sub(r"^\s*<img[^>]*>\s*(<br\s*/?>)?[^\n]*\n", "", bruto)
            bruto = re.sub(r"^\s*[^\n.]{1,70}\n", "", bruto)
        resumo = limpar(bruto)
        if resumo.lower().startswith(titulo.lower()[:40]):
            resumo = resumo[len(titulo):].strip(" -–—:")
        itens.append({"link": link.split("#")[0], "titulo": titulo, "resumo": resumo, "quando": quando,
                      "cat": cat, "peso": peso, "regional": regional, "fonte": fonte_do_link(link, chave)})
    print(f"  {len(itens):3d} itens  {url}")
    return itens


def tokens(titulo):
    return {w for w in re.findall(r"[a-z0-9]+", sem_acento(titulo)) if len(w) > 2 and w not in STOPWORDS}


def agrupar(itens):
    """Junta matérias de portais diferentes sobre o mesmo fato (similaridade TF-IDF dos títulos)."""
    df = Counter(t for it in itens for t in it["tok"])
    n = len(itens)
    for it in itens:
        vec = {t: math.log(n / df[t]) + 1 for t in it["tok"]}
        norma = math.sqrt(sum(v * v for v in vec.values())) or 1
        it["vec"] = {t: v / norma for t, v in vec.items()}

    grupos = []
    for it in sorted(itens, key=lambda x: x["quando"], reverse=True):
        melhor, nota = None, 0.0
        for g in grupos:
            cos = max(sum(v * m["vec"].get(t, 0) for t, v in it["vec"].items()) for m in g[:4])
            if cos > nota:
                melhor, nota = g, cos
        if melhor is not None and nota >= 0.32:
            melhor.append(it)
        else:
            grupos.append([it])
    return grupos


def selecionar(itens, agora):
    por_link = {}
    for it in itens:
        chave = re.sub(r"^https?://(www\d?\.)?", "", it["link"]).rstrip("/")
        if chave not in por_link or it["peso"] > por_link[chave]["peso"]:
            por_link[chave] = it
    unicos = list(por_link.values())
    for it in unicos:
        it["quando"] = it["quando"] or agora
        it["tok"] = tokens(it["titulo"])

    recentes = [it for it in unicos if agora - it["quando"] <= timedelta(hours=72)]
    grupos = []
    for membros in agrupar(recentes):
        fontes = {m["fonte"] for m in membros}
        if len(fontes) < 2 and all(m["regional"] for m in membros):
            continue
        linhas = {FONTES[f]["linha"] for f in fontes}
        votos = Counter()
        for m in membros:
            votos[m["cat"]] += m["peso"]
        cat = votos.most_common(1)[0][0]
        idade = (agora - max(m["quando"] for m in membros)).total_seconds() / 3600
        nota = len(fontes) + 0.5 * len(linhas) + max(0, 1 - idade / 24)
        grupos.append({"cat": cat, "nota": nota, "idade": idade, "membros": membros})

    return {cat: escolher_editoria([g for g in grupos if g["cat"] == cat], i)
            for i, (cat, _, _) in enumerate(EDITORIAS)}


def parecido(a, b):
    return sum(v * b["vec"].get(t, 0) for t, v in a["vec"].items()) >= 0.25


def escolher_editoria(grupos, rodada):
    """Alterna entre linhas editoriais; cada uma contribui com os fatos de maior repercussão que cobriu."""
    linhas = ["centro", "esquerda", "centro-direita"]
    linhas = linhas[rodada % 3:] + linhas[:rodada % 3]
    por_linha = {}
    for l in linhas:
        da_linha = [g for g in grupos if any(FONTES[m["fonte"]]["linha"] == l for m in g["membros"])]
        # Matérias do último dia primeiro; mais antigas só se a linha não tiver o suficiente.
        por_linha[l] = sorted(da_linha, key=lambda g: (g["idade"] > 24, -g["nota"]))
    usados, uso_fonte, escolhidos = set(), Counter(), []
    # Se faltar notícia com o limite normal por portal, as passadas seguintes aceitam mais de cada um.
    for limite in (MAX_POR_FONTE, MAX_POR_FONTE + 2, POR_EDITORIA):
        filas = {l: list(fila) for l, fila in por_linha.items()}
        while len(escolhidos) < POR_EDITORIA and any(filas.values()):
            for linha in linhas:
                if len(escolhidos) >= POR_EDITORIA:
                    break
                fila = filas[linha]
                while fila:
                    g = fila.pop(0)
                    if id(g) in usados or any(parecido(g["membros"][0], e) for e in escolhidos):
                        continue
                    # O representante precisa ser da mesma editoria, salvo se a dele veio só de palpite.
                    opcoes = [m for m in g["membros"] if FONTES[m["fonte"]]["linha"] == linha
                              and uso_fonte[m["fonte"]] < limite and (m["cat"] == g["cat"] or m["peso"] < 3)]
                    if not opcoes:
                        continue
                    m = min(opcoes, key=lambda m: (uso_fonte[m["fonte"]], -len(m["resumo"])))
                    usados.add(id(g))
                    uso_fonte[m["fonte"]] += 1
                    escolhidos.append({**m, "nota": g["nota"]})
                    break
    return sorted(escolhidos, key=lambda m: m["nota"], reverse=True)


def corpo_jsonld(pagina):
    for bloco in re.findall(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", pagina, re.S | re.I):
        try:
            pilha = [json.loads(bloco.strip())]
        except ValueError:
            continue
        while pilha:
            d = pilha.pop()
            if isinstance(d, list):
                pilha.extend(d)
            elif isinstance(d, dict):
                if isinstance(d.get("articleBody"), str):
                    return limpar(d["articleBody"])
                pilha.extend(v for v in d.values() if isinstance(v, (dict, list)))
    return ""


# Estadão, g1/Valor e Terra marcam os parágrafos do texto; a Folha usa itemprop="articleBody" no contêiner.
MARCA_PARAGRAFO = re.compile(r'data-component-name="paragraph"|content-text__container|class="text"')


def paragrafos_do_corpo(pagina):
    marcados = bool(MARCA_PARAGRAFO.search(pagina))
    inicio = pagina.find('itemprop="articleBody"')
    if not marcados and inicio < 0:
        return ""
    textos = []
    for attrs, miolo in re.findall(r"<p\b([^>]*)>(.*?)</p>", pagina[max(inicio, 0):], re.S | re.I):
        if marcados and not MARCA_PARAGRAFO.search(attrs):
            continue
        texto = limpar(miolo)
        if len(texto) >= 60:
            textos.append(texto)
        if sum(map(len, textos)) >= 500:
            break
    return " ".join(textos)


def trecho_da_pagina(url):
    """Início da matéria (JSON-LD ou parágrafos marcados) ou, se não houver, a linha fina (og:description)."""
    try:
        pagina = baixar(url, timeout=20).decode("utf-8", "ignore")
    except Exception:
        return ""
    corpo = corpo_jsonld(pagina)
    if len(corpo) < MIN_RESUMO:
        corpo = paragrafos_do_corpo(pagina)
    if len(corpo) >= MIN_RESUMO:
        return corpo
    og = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']+)',
                   pagina, re.I)
    return limpar(og.group(1)) if og else corpo


def completar_resumos(selecao):
    faltando = [it for lista in selecao.values() for it in lista if len(it["resumo"]) < MIN_RESUMO]
    with cf.ThreadPoolExecutor(12) as ex:
        for it, texto in zip(faltando, ex.map(lambda it: trecho_da_pagina(it["link"]), faltando)):
            if len(texto) > len(it["resumo"]):
                it["resumo"] = texto


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]


def renderizar(selecao, agora):
    e = html.escape
    secoes, menu, letreiro = [], [], []
    for cat, nome, cor in EDITORIAS:
        menu.append(f'<a href="#{cat}" style="--cor:{cor}">{e(nome)}</a>')
        itens = selecao.get(cat, [])
        if itens:
            letreiro.append(f'<b>{e(nome)}:</b> <a href="{e(itens[0]["link"])}" target="_blank" rel="noopener">'
                            f'{e(itens[0]["titulo"])}</a>')
        lis = []
        for i, it in enumerate(itens):
            lis.append(
                f'<li class="{"lead" if i == 0 else ""}">'
                f'<a class="manchete" href="{e(it["link"])}" target="_blank" rel="noopener">{e(it["titulo"])}</a>'
                f'<p>{e(cortar(it["resumo"]))}</p>'
                f'<span class="fonte">{e(FONTES[it["fonte"]]["nome"])}</span></li>')
        corpo = "\n".join(lis) or '<li class="vazio">Nenhuma notícia encontrada hoje.</li>'
        secoes.append(
            f'<section class="box" id="{cat}" style="--cor:{cor}">'
            f'<h2><span>&raquo; {e(nome)}</span><a href="#topo">topo &uarr;</a></h2>'
            f'<ol>\n{corpo}\n</ol></section>')

    fontes = "\n".join(f'<li><a href="https://{f["site"]}" target="_blank" rel="noopener">{e(f["nome"])}</a></li>'
                       for f in sorted(FONTES.values(), key=lambda f: sem_acento(f["nome"])))
    canais = "\n".join(f'<li><a href="#{c}" style="color:{cor}">{e(n)}</a></li>' for c, n, cor in EDITORIAS)

    data = f"{DIAS[agora.weekday()].capitalize()}, {agora.day} de {MESES[agora.month - 1]} de {agora.year}"
    trocas = {
        "{{DATA}}": e(data),
        "{{ATUALIZADO}}": agora.strftime("%d/%m/%Y, %Hh%M"),
        "{{MENU}}": "\n".join(menu),
        "{{LETREIRO}}": " &nbsp;&bull;&nbsp; ".join(letreiro),
        "{{SECOES}}": "\n".join(secoes),
        "{{CANAIS}}": canais,
        "{{FONTES}}": fontes,
        "{{ANO}}": str(agora.year),
    }
    pagina = (RAIZ / "template.html").read_text(encoding="utf-8")
    for k, v in trocas.items():
        pagina = pagina.replace(k, v)
    return pagina


def main():
    agora = datetime.now(BRT).replace(second=0, microsecond=0)
    print("Lendo feeds...")
    tarefas = [(chave, url, cat) for chave, f in FONTES.items() for url, cat in f["feeds"]]
    with cf.ThreadPoolExecutor(12) as ex:
        itens = [it for lote in ex.map(lambda t: ler_feed(*t), tarefas) for it in lote]
    if len(itens) < 100:
        sys.exit(f"Só {len(itens)} itens lidos; mantendo a página anterior.")

    selecao = selecionar(itens, agora.astimezone(timezone.utc))
    completar_resumos(selecao)

    for cat, nome, _ in EDITORIAS:
        print(f"\n{nome}: {len(selecao.get(cat, []))}")
        for it in selecao.get(cat, []):
            print(f"  [{FONTES[it['fonte']]['linha']:14}] {FONTES[it['fonte']]['nome'][:16]:16} {it['nota']:.1f} {it['titulo'][:80]}")

    saida = RAIZ / "docs" / "index.html"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(renderizar(selecao, agora), encoding="utf-8")
    print(f"\nGerado {saida}")


if __name__ == "__main__":
    main()
