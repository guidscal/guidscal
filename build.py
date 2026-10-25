"""
Génère les visuels SVG du profil GitHub.
Les polices de ton site (Syne, Anonymous Pro, Stack Sans) sont intégrées dans chaque SVG :
GitHub n'autorise pas le chargement de polices externes dans une image.

Usage : python3 build.py [dossier_des_polices]   (défaut : ./fonts, fichiers .ttf / .otf / .woff)
"""
import os, sys, glob, io, base64
from fontTools.ttLib import TTFont
from fontTools import subset as ftsubset

FONT_DIR = sys.argv[1] if len(sys.argv) > 1 else "fonts"
CYAN="#6bdfff"; MAG="#ff2bd6"; BG="#282828"; BLUE="#0a8fd8"

# famille -> pile de secours si la police n'est pas fournie
FALLBACK = {
  "Syne": "'Arial Black','Segoe UI',Arial,sans-serif",
  "Anonymous Pro": "'Courier New',monospace",
  "Stack Sans Headline": "'Segoe UI','Helvetica Neue',Arial,sans-serif",
  "Stack Sans Text": "'Segoe UI','Helvetica Neue',Arial,sans-serif",
}
def ff(family): return f"'{family}',{FALLBACK[family]}"

os.makedirs("assets", exist_ok=True)
def w(name, txt): open(f"assets/{name}", "w", encoding="utf-8").write(txt)

# ---------------------------------------------------------------- polices
_cache = {}
def _scan():
    if "files" in _cache: return _cache["files"]
    files = []
    for p in glob.glob(os.path.join(FONT_DIR, "**", "*.*"), recursive=True):
        if p.lower().endswith((".ttf", ".otf", ".woff")):
            try:
                f = TTFont(p, lazy=True)
                nm = f["name"]
                fam = (nm.getDebugName(16) or nm.getDebugName(1) or "").strip()
                files.append((p, fam, f))
            except Exception:
                pass
    _cache["files"] = files
    return files

def find_font(family, weight=400, italic=False):
    """Meilleure correspondance dans le dossier de polices, ou None."""
    best, best_score = None, 1e9
    for p, fam, f in _scan():
        if family.lower().replace(" ", "") not in fam.lower().replace(" ", ""):
            continue
        is_it = bool(f["OS/2"].fsSelection & 1) or "italic" in p.lower() or "italic" in (f["name"].getDebugName(2) or "").lower()
        wght = f["OS/2"].usWeightClass
        if "fvar" in f:
            ax = [a for a in f["fvar"].axes if a.axisTag == "wght"]
            score = 0 if ax and ax[0].minValue <= weight <= ax[0].maxValue else 500
        else:
            score = abs(wght - weight)
        score += 0 if is_it == italic else 1000
        if score < best_score: best, best_score = p, score
    return best

def make_face(family, weight, italic, chars):
    """Sous-ensemble WOFF (base64) limité aux caractères utilisés, ou None."""
    path = find_font(family, weight, italic)
    if not path: return None, None
    font = TTFont(path)
    if "fvar" in font:
        from fontTools.varLib import instancer
        axes = {a.axisTag: a for a in font["fvar"].axes}
        loc = {"wght": max(axes["wght"].minValue, min(axes["wght"].maxValue, weight))} if "wght" in axes else {}
        for tag, a in axes.items():       # figer les autres axes à leur valeur par défaut
            if tag != "wght": loc[tag] = a.defaultValue
        font = instancer.instantiateVariableFont(font, loc)
    opts = ftsubset.Options(); opts.flavor = "woff"; opts.layout_features = ["kern", "liga"]
    opts.notdef_outline = True; opts.name_IDs = [1, 2]; opts.drop_tables += ["DSIG"]
    sub = ftsubset.Subsetter(opts); sub.populate(text="".join(sorted(set(chars)))); sub.subset(font)
    buf = io.BytesIO(); font.flavor = "woff"; font.save(buf)
    return base64.b64encode(buf.getvalue()).decode(), font

def text_width(font, text, size):
    """Largeur naturelle d'un texte (avances des glyphes, sans crénage)."""
    cmap = font.getBestCmap(); hmtx = font["hmtx"]; upm = font["head"].unitsPerEm
    return sum(hmtx[cmap[ord(c)]][0] for c in text if ord(c) in cmap) * size / upm

def embed(svg, specs):
    """specs : [(famille, graisse, italique, "texte utilisé")]. Insère les @font-face."""
    css = ""
    for fam, wt, it, chars in specs:
        b64, _ = make_face(fam, wt, it, chars)
        if b64:
            css += (f"@font-face{{font-family:'{fam}';font-weight:{wt};font-style:{'italic' if it else 'normal'};"
                    f"src:url(data:font/woff;base64,{b64}) format('woff')}}")
    if not css: return svg
    return svg.replace("<style>", f"<style>{css}", 1)

def fit(family, weight, italic, text, target, default):
    """Taille de police pour que `text` mesure `target` px (si la police est fournie)."""
    _, font = make_face(family, weight, italic, text)
    return (target / text_width(font, text, 1)) if font else default

# ---------------------------------------------------------------- filtres
# Style du titre : "outline" (contour, comme ton hero) ou "fill" (rempli, plus lisible)
HERO_STYLE = os.environ.get("HERO_STYLE", "outline")
GLOW = float(os.environ.get("GLOW", "0.55"))     # 0 = aucune lueur, 1 = forte
NEON=f'''<filter id="neon" x="-20%" y="-60%" width="140%" height="220%">
  <feGaussianBlur in="SourceGraphic" stdDeviation="{1.5+2*GLOW:.1f}" result="blur"/>
  <feColorMatrix in="blur" type="matrix" values="0 0 0 0 0.42  0 0 0 0 0.87  0 0 0 0 1  0 0 0 {GLOW:.2f} 0" result="glow"/>
  <feMerge><feMergeNode in="glow"/><feMergeNode in="SourceGraphic"/></feMerge>
</filter>'''
SOFT='''<filter id="soft" x="-10%" y="-10%" width="120%" height="120%">
  <feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
</filter>'''

# ---------------------------------------------------------------- bannière (héro du hub)
if HERO_STYLE == "fill":
    LOGO_PAINT = f"fill:#e9fbff;stroke:{CYAN};stroke-width:1.5;stroke-linejoin:round;paint-order:stroke"
else:
    LOGO_PAINT = f"fill:rgba(107,223,255,.16);stroke:{CYAN};stroke-width:2.5;stroke-linejoin:round;paint-order:stroke" 
T1, T2, T3 = "Guillaume Callebert", "Dev Web/Jeu", "Un développeur social et impliqué!"
S1 = fit("Syne", 800, False, T1, 800, 62)       # titre : 800 px de large
S2 = fit("Syne", 800, False, T2, 440, 44)       # sous-titre : 440 px
banner=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 300" width="1000" height="300" role="img" aria-labelledby="t d">
<title id="t">Guillaume Callebert, Dev Web/Jeu</title>
<desc id="d">Un développeur social et impliqué</desc>
<defs>
{NEON}
{SOFT}
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0a84c6"/><stop offset="1" stop-color="#1d4766"/></linearGradient>
<pattern id="lines" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" fill-opacity="0.07"/></pattern>
<clipPath id="round"><rect width="1000" height="300" rx="24"/></clipPath>
</defs>
<style>
.logo{{font-family:{ff("Syne")};font-weight:800;{LOGO_PAINT}}}
.t1{{font-size:{S1:.1f}px}} .t2{{font-size:{S2:.1f}px}}
.tag{{font-family:{ff("Anonymous Pro")};font-style:italic;font-size:24px;letter-spacing:1.5px;fill:#fff}}
.fx{{transform-box:fill-box;transform-origin:center}}
.gm{{fill:none;stroke:{MAG};mix-blend-mode:screen;opacity:0;animation:gm 5s infinite steps(1,end)}}
.gc{{fill:none;stroke:#00fff0;mix-blend-mode:screen;opacity:0;animation:gc 5s infinite steps(1,end)}}
.gb{{animation:gb 5s infinite steps(1,end)}}
.flick{{animation:flick 7s infinite steps(1,end)}}
@keyframes gm{{0%,86%,100%{{transform:translate(0,0);opacity:0}}87%{{transform:translate(-8px,1px);opacity:.9}}89%{{transform:translate(6px,-1px);opacity:.9}}91%{{transform:translate(-4px,0);opacity:.75}}93%{{transform:translate(2px,1px);opacity:.6}}95%{{transform:translate(0,0);opacity:0}}}}
@keyframes gc{{0%,86%,100%{{transform:translate(0,0);opacity:0}}87%{{transform:translate(8px,-1px);opacity:.9}}89%{{transform:translate(-6px,1px);opacity:.9}}91%{{transform:translate(4px,0);opacity:.75}}93%{{transform:translate(-2px,-1px);opacity:.6}}95%{{transform:translate(0,0);opacity:0}}}}
@keyframes gb{{0%,86%,95%,100%{{transform:translate(0,0) skewX(0)}}88%{{transform:translate(2px,0) skewX(-7deg)}}90%{{transform:translate(-2px,0) skewX(6deg)}}92%{{transform:translate(1px,0) skewX(-3deg)}}}}
@keyframes flick{{0%,18%,21%,24%,56%,58%,100%{{opacity:1}}19%,22%,57%{{opacity:.3}}}}
@media (prefers-reduced-motion:reduce){{.gm,.gc,.gb,.flick{{animation:none}}}}
</style>
<g clip-path="url(#round)">
  <rect width="1000" height="300" fill="url(#bg)"/>
  <rect width="1000" height="300" fill="url(#lines)"/>
</g>
<g text-anchor="middle">
  <g class="gb fx">
    <text class="logo t1 gm fx" x="500" y="128">{T1}</text>
    <text class="logo t1 gc fx" x="500" y="128">{T1}</text>
    <text class="logo t1" x="500" y="128" filter="url(#neon)">{T1}</text>
  </g>
  <text class="logo t2 flick" x="500" y="205" filter="url(#neon)">{T2}</text>
  <text class="tag" x="500" y="260">{T3}</text>
</g>
</svg>'''
w("banner.svg", embed(banner, [("Syne",800,False,T1+T2), ("Anonymous Pro",400,True,T3)]))

# ---------------------------------------------------------------- diviseur
divider=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 20" width="900" height="20" role="presentation" aria-hidden="true">
<defs>
<linearGradient id="l" x1="0" x2="1"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset="0.3" stop-color="{CYAN}"/><stop offset="0.5" stop-color="{MAG}"/><stop offset="0.7" stop-color="{CYAN}"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>
{SOFT}
</defs>
<style>.d{{animation:p 3.5s ease-in-out infinite}}@keyframes p{{0%,100%{{opacity:.55}}50%{{opacity:1}}}}@media (prefers-reduced-motion:reduce){{.d{{animation:none}}}}</style>
<g class="d" filter="url(#soft)"><rect x="40" y="9" width="820" height="2" rx="1" fill="url(#l)"/>
<path d="M450 3L457 10L450 17L443 10Z" fill="{BG}" stroke="{MAG}" stroke-width="1.5"/></g>
</svg>'''
w("divider.svg", divider)

# ---------------------------------------------------------------- statut
L1a, L1b = "Actuellement à la recherche d’un stage en ", "développement web"
L2a, L2b, L2c, L2d, L2e = "ou en ", "développement de jeux vidéo", ", à partir de ", "mars 2027", "."
status=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 130" width="900" height="130" role="img" aria-labelledby="t">
<title id="t">À la recherche d'un stage en développement web ou en développement de jeux vidéo à partir de mars 2027</title>
<defs>{SOFT}</defs>
<style>
text{{font-family:{ff("Stack Sans Text")};font-size:21px;fill:#e9eef0}}
.b{{font-weight:600;fill:{CYAN}}}
.pulse{{transform-box:fill-box;transform-origin:center;animation:pulse 2s ease-out infinite}}
@keyframes pulse{{0%{{transform:scale(1);opacity:.8}}100%{{transform:scale(2.6);opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.pulse{{animation:none}}}}
</style>
<rect x="2" y="2" width="896" height="126" rx="24" fill="#333" stroke="{CYAN}" stroke-opacity="0.5" stroke-width="2" filter="url(#soft)"/>
<g transform="translate(46 65)"><circle class="pulse" r="9" fill="{CYAN}"/><circle r="9" fill="{CYAN}" filter="url(#soft)"/></g>
<text x="86" y="53">{L1a}<tspan class="b">{L1b}</tspan></text>
<text x="86" y="88">{L2a}<tspan class="b">{L2b}</tspan>{L2c}<tspan class="b">{L2d}</tspan>{L2e}</text>
</svg>'''
allc = L1a+L1b+L2a+L2b+L2c+L2d+L2e
w("status.svg", embed(status, [("Stack Sans Text",400,False,allc), ("Stack Sans Text",600,False,L1b+L2b+L2d)]))

# ---------------------------------------------------------------- compétences
rows=[("WEB",CYAN,["HTML","CSS / SCSS","JavaScript","PHP","WordPress"]),
      ("JEU",MAG,["Unreal Engine","Blueprints","Unity","C#","Blender"]),
      ("OUTILS","#c9d3d7",["Git / GitHub","Figma"])]
chips=[]; y=26; used=""
for label,col,items in rows:
    chips.append(f'<text x="34" y="{y+26}" class="lab" fill="{col}">{label}</text>'); used+=label
    x=150
    for it in items:
        wd=int(len(it)*9.4+34); used+=it
        chips.append(f'<g><rect x="{x}" y="{y}" width="{wd}" height="40" rx="20" fill="#ffffff" fill-opacity="0.04" stroke="{col}" stroke-width="1.6" filter="url(#soft)"/>'
                     f'<text x="{x+wd/2}" y="{y+26}" text-anchor="middle" class="chip">{it}</text></g>')
        x+=wd+12
    y+=62
H=y+10
skills=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 {H}" width="900" height="{H}" role="img" aria-label="Compétences : HTML, CSS/SCSS, JavaScript, PHP, WordPress, Unreal Engine, Blueprints, Unity, C#, Blender, Git/GitHub, Figma">
<defs>{SOFT}</defs>
<style>.lab{{font-family:{ff("Anonymous Pro")};font-size:17px;font-weight:700;letter-spacing:4px}} .chip{{font-family:{ff("Stack Sans Headline")};font-size:16px;font-weight:600;fill:#f2f7f8}}</style>
<rect x="2" y="2" width="896" height="{H-4}" rx="24" fill="{BG}" stroke="#ffffff" stroke-opacity="0.08" stroke-width="2"/>
{chr(10).join(chips)}
</svg>'''
w("skills.svg", embed(skills, [("Anonymous Pro",700,False,"WEBJEUOUTILS"), ("Stack Sans Headline",600,False,used)]))

# ---------------------------------------------------------------- boutons
def button(name,label):
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 64" width="210" height="64" role="img" aria-label="{label}">
<defs>{SOFT}</defs>
<style>text{{font-family:{ff("Stack Sans Headline")};font-size:20px;font-weight:600;fill:#fff}}</style>
<rect x="4" y="6" width="202" height="52" rx="14" fill="{BLUE}" stroke="{CYAN}" stroke-width="1.6" filter="url(#soft)"/>
<text x="26" y="39">{label}</text>
<circle cx="172" cy="32" r="17" fill="#fff"/>
<path d="M164 32H180M174 25L181 32L174 39" fill="none" stroke="{BLUE}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''
    w(f"btn-{name}.svg", embed(svg, [("Stack Sans Headline",600,False,label)]))
for n,l in [("portfolio","Portfolio"),("linkedin","LinkedIn"),("courriel","Courriel"),("cv","Mon CV")]:
    button(n,l)

found = [f"{fam}" for _, fam, _ in _scan()]
print("Polices trouvées :", sorted(set(found)) or "aucune (polices de secours utilisées)")
