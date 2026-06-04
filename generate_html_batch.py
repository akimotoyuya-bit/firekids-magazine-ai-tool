#!/usr/bin/env python3
"""Generate WordPress Gutenberg HTML from TXT articles for FIRE KIDS Magazine."""
import re, os
from pathlib import Path

# プロジェクトルート（このスクリプトの親ディレクトリ）を自動判定
# 旧Mac環境: /Users/sasakitasuku/.../MAGAZINE
# 新Windows環境: スクリプトと同じ場所（FirekidsMagazine-main/）
BASE = str(Path(__file__).resolve().parent)

BRAND_IMAGES = {
    "IWC": [
        "https://cdn.firekids.jp/products/13132/13132_1_137274.jpg",
        "https://cdn.firekids.jp/products/13118/13118_1_136835.jpg",
        "https://cdn.firekids.jp/products/13011/13011_1_135977.jpg",
        "https://cdn.firekids.jp/products/13010/13010_1_135644.jpg",
        "https://cdn.firekids.jp/products/12926/12926_1_136428.jpg",
        "https://cdn.firekids.jp/products/12891/12891_1_133841.jpg",
        "https://cdn.firekids.jp/products/12866/12866_1_133908.jpg",
        "https://cdn.firekids.jp/products/12728/12728_1_131889.jpg",
        "https://cdn.firekids.jp/products/12690/12690_1_131697.jpg",
        "https://cdn.firekids.jp/products/12689/12689_1_131688.jpg",
        "https://cdn.firekids.jp/products/12688/12688_1_131676.jpg",
        "https://cdn.firekids.jp/products/12635/12635_1_130972.jpg",
        "https://cdn.firekids.jp/products/12501/12501_1.jpg",
        "https://cdn.firekids.jp/products/12350/12350_1.jpg",
        "https://cdn.firekids.jp/products/12115/1.jpg",
        "https://cdn.firekids.jp/products/11984/1.jpg",
        "https://cdn.firekids.jp/products/11943/11943_1_128646.jpg",
        "https://cdn.firekids.jp/products/11900/1.jpg",
        "https://cdn.firekids.jp/products/11896/11896_1.jpg",
        "https://cdn.firekids.jp/products/11805/11805_1.jpg",
        "https://cdn.firekids.jp/products/11628/11628_1.jpg",
        "https://cdn.firekids.jp/products/11625/0172-32928.jpg",
        "https://cdn.firekids.jp/products/11624/124A7102.jpg",
        "https://cdn.firekids.jp/products/11570/0172-32948.jpg",
        "https://cdn.firekids.jp/products/11565/11565_1_133979.jpg",
        "https://cdn.firekids.jp/products/11391/11391_1_137182.jpg",
        "https://cdn.firekids.jp/products/11390/11390_1_136333.jpg",
        "https://cdn.firekids.jp/products/11335/5G1A2753_3423cbeb-bfa9-4bd4-ba0a-0a9e595add76.jpg",
        "https://cdn.firekids.jp/products/11306/11306_1_134186.jpg",
        "https://cdn.firekids.jp/products/11248/11248_1_135009.jpg",
        "https://cdn.firekids.jp/products/11247/1.jpg",
        "https://cdn.firekids.jp/products/11145/0170-32409.jpg",
        "https://cdn.firekids.jp/products/11123/11123_1_134056.jpg",
        "https://cdn.firekids.jp/products/10952/Maz_4977.jpg",
        "https://cdn.firekids.jp/products/10860/124A4056_a027b59d-cccd-4fbc-b0ba-850822bb60fc.jpg",
        "https://cdn.firekids.jp/products/10471/5G1A9313_ac2e4999-9089-4eef-bf74-42e686f69df1.jpg",
    ],
    "JLC": [
        "https://cdn.firekids.jp/products/12815/12815_1_132990.jpg",
        "https://cdn.firekids.jp/products/12650/12650_1_130665.jpg",
        "https://cdn.firekids.jp/products/12458/12458_1_128086.jpg",
        "https://cdn.firekids.jp/products/12179/1.jpg",
        "https://cdn.firekids.jp/products/11844/1.jpg",
        "https://cdn.firekids.jp/products/11193/124A4957.jpg",
        "https://cdn.firekids.jp/products/11088/124A4947_d95148fc-087f-48b8-8280-016e0ef6abf7.jpg",
        "https://cdn.firekids.jp/products/10855/5G1A2573_05272cf8-1ec7-402c-99ef-d672df982eb0.jpg",
        "https://cdn.firekids.jp/products/10583/10583_1.jpg",
        "https://cdn.firekids.jp/products/9852/124A5378.jpg",
        "https://cdn.firekids.jp/products/9210/24A0447_8f0138cd-cafc-48a6-b330-677d41c56482.jpg",
        "https://cdn.firekids.jp/products/7234/0064-7920.jpg",
        "https://cdn.firekids.jp/products/7116/7116_1_133808.jpg",
        "https://cdn.firekids.jp/products/5009/054-47385.jpg",
        "https://cdn.firekids.jp/products/9338/0118-19861.jpg",
        "https://cdn.firekids.jp/products/5064/057-48094.jpg",
        "https://cdn.firekids.jp/products/12900/12900_1_133881.jpg",
        "https://cdn.firekids.jp/products/12176/1.jpg",
    ],
    "LONGINES": [
        "https://cdn.firekids.jp/products/13175/13175_1_137529.jpg",
        "https://cdn.firekids.jp/products/13058/13058_1_136229.jpg",
        "https://cdn.firekids.jp/products/12945/12945_1_135351.jpg",
        "https://cdn.firekids.jp/products/12709/12709_1_131504.jpg",
        "https://cdn.firekids.jp/products/12477/12477_1_134206.jpg",
        "https://cdn.firekids.jp/products/12341/12341_1_130146.jpg",
        "https://cdn.firekids.jp/products/12165/1.jpg",
        "https://cdn.firekids.jp/products/12149/1.jpg",
        "https://cdn.firekids.jp/products/11991/1.jpg",
        "https://cdn.firekids.jp/products/11927/1.jpg",
        "https://cdn.firekids.jp/products/11814/11814_1_135263.jpg",
        "https://cdn.firekids.jp/products/11622/5G1A5017_202f9df9-ffd2-463c-9ce1-1eda13f8666e.jpg",
        "https://cdn.firekids.jp/products/11621/11621_1_136526.jpg",
        "https://cdn.firekids.jp/products/11436/11436_1_136366.jpg",
        "https://cdn.firekids.jp/products/11343/124A6519_74f1856a-0565-48a1-b706-13e2cf831d2a.jpg",
        "https://cdn.firekids.jp/products/11128/0166-31359.jpg",
        "https://cdn.firekids.jp/products/11117/124A4653_1cfa6d42-de90-4d7a-959c-11a2a95eca54.jpg",
        "https://cdn.firekids.jp/products/11116/5G1A1741_415f6db1-f1e1-4d5b-8935-a83309121884.jpg",
    ],
    "CARTIER": [
        "https://cdn.firekids.jp/products/12906/12906_1_134399.jpg",
        "https://cdn.firekids.jp/products/12323/12323_1_128332.jpg",
        "https://cdn.firekids.jp/products/12006/1.jpg",
        "https://cdn.firekids.jp/products/11743/11743_1.jpg",
        "https://cdn.firekids.jp/products/11682/1.jpg",
        "https://cdn.firekids.jp/products/11513/11513_1.jpg",
        "https://cdn.firekids.jp/products/11444/5G1A3225_3d4d31ff-f3ea-4f31-8943-a2bb3b67518b.jpg",
        "https://cdn.firekids.jp/products/11010/11010_1_130877.jpg",
        "https://cdn.firekids.jp/products/10689/Maz_6898.jpg",
        "https://cdn.firekids.jp/products/10688/5G1A9013_07f1ce20-e0b0-4aa1-b876-836a9b928810.jpg",
        "https://cdn.firekids.jp/products/10429/5G1A8625.jpg",
        "https://cdn.firekids.jp/products/10354/1.jpg",
        "https://cdn.firekids.jp/products/10322/5G1A8011_3c304186-1a37-492d-959e-f82dbfe9a11b.jpg",
        "https://cdn.firekids.jp/products/10160/5G1A6646_6bb31bef-c343-44c7-be3d-494898980a6b.jpg",
        "https://cdn.firekids.jp/products/10027/5G1A5995_cf7e7e01-9fde-4425-bf38-84025276b3fd.jpg",
    ],
    "CITIZEN": [
        "https://cdn.firekids.jp/products/13176/13176_1_137538.jpg",
        "https://cdn.firekids.jp/products/13126/13126_1_137238.jpg",
        "https://cdn.firekids.jp/products/13050/13050_1_136085.jpg",
        "https://cdn.firekids.jp/products/13029/13029_1_135881.jpg",
        "https://cdn.firekids.jp/products/12962/12962_1_135125.jpg",
        "https://cdn.firekids.jp/products/12830/12830_1_133634.jpg",
        "https://cdn.firekids.jp/products/12824/12824_1_133531.jpg",
        "https://cdn.firekids.jp/products/12818/12818_1_133022.jpg",
        "https://cdn.firekids.jp/products/12816/12816_1_133001.jpg",
        "https://cdn.firekids.jp/products/12740/12740_1_132038.jpg",
        "https://cdn.firekids.jp/products/12441/12441_1.jpg",
        "https://cdn.firekids.jp/products/12285/12285_1.jpg",
        "https://cdn.firekids.jp/products/12272/1.jpg",
        "https://cdn.firekids.jp/products/11791/1.jpg",
        "https://cdn.firekids.jp/products/11790/1.jpg",
    ],
    "UNIVERSAL": [
        "https://cdn.firekids.jp/products/13065/13065_1_138074.jpg",
        "https://cdn.firekids.jp/products/12999/12999_1_135814.jpg",
        "https://cdn.firekids.jp/products/12998/12998_1_135960.jpg",
        "https://cdn.firekids.jp/products/12471/12471_1.jpg",
        "https://cdn.firekids.jp/products/12312/12312_1.jpg",
        "https://cdn.firekids.jp/products/12247/12247_1.jpg",
        "https://cdn.firekids.jp/products/12182/1.jpg",
        "https://cdn.firekids.jp/products/12180/12180_1_135272.jpg",
        "https://cdn.firekids.jp/products/11981/1.jpg",
        "https://cdn.firekids.jp/products/11668/11668_1.jpg",
        "https://cdn.firekids.jp/products/11215/11215_1_130649.jpg",
        "https://cdn.firekids.jp/products/11133/0169-32141.jpg",
    ],
    "ORIENT": [
        "https://cdn.firekids.jp/products/13048/13048_1_136201.jpg",
        "https://cdn.firekids.jp/products/12889/12889_1_133788.jpg",
        "https://cdn.firekids.jp/products/12583/12583_1_130392.jpg",
        "https://cdn.firekids.jp/products/11635/Maz_7082.jpg",
        "https://cdn.firekids.jp/products/11607/0171-32729.jpg",
        "https://cdn.firekids.jp/products/11166/0170-32388.jpg",
    ],
    "BREITLING": [
        "https://cdn.firekids.jp/products/13060/13060_1_136731.jpg",
        "https://cdn.firekids.jp/products/12893/12893_1_134133.jpg",
        "https://cdn.firekids.jp/products/12892/12892_1_133853.jpg",
    ],
}

CTA_LINKS = {
    "IWC": "https://firekids.jp/products/list?category_id=12&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic",
    "JLC": "https://firekids.jp/products/list?category_id=16&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic",
    "LONGINES": "https://firekids.jp/products/list?category_id=15&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic",
    "CARTIER": "https://firekids.jp/products/list?category_id=17&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic",
    "CITIZEN": "https://firekids.jp/products/list?category_id=11&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic",
    "UNIVERSAL": "https://firekids.jp/products/list?category_id=18&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic",
    "ORIENT": "https://firekids.jp/products/list?category_id=14&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic",
    "BREITLING": "https://firekids.jp/products/list?category_id=19&utm_source=firekids_magazine&utm_medium=seo&utm_campaign=organic",
}
CTA_LABELS = {"IWC":"FIRE KIDS IWC\u306e\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b","JLC":"FIRE KIDS \u30b8\u30e3\u30ac\u30fc\u30fb\u30eb\u30af\u30eb\u30c8\u306e\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b","LONGINES":"FIRE KIDS \u30ed\u30f3\u30b8\u30f3\u306e\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b","CARTIER":"FIRE KIDS \u30ab\u30eb\u30c6\u30a3\u30a8\u306e\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b","CITIZEN":"FIRE KIDS \u30b7\u30c1\u30ba\u30f3\u306e\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b","UNIVERSAL":"FIRE KIDS \u30e6\u30cb\u30d0\u30fc\u30b5\u30eb\u30b8\u30e5\u30cd\u30fc\u30d6\u306e\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b","ORIENT":"FIRE KIDS \u30aa\u30ea\u30a8\u30f3\u30c8\u306e\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b","BREITLING":"FIRE KIDS \u30d6\u30e9\u30a4\u30c8\u30ea\u30f3\u30b0\u306e\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b"}
BRAND_NAMES_JP = {"IWC":"IWC","JLC":"\u30b8\u30e3\u30ac\u30fc\u30fb\u30eb\u30af\u30eb\u30c8","LONGINES":"\u30ed\u30f3\u30b8\u30f3","CARTIER":"\u30ab\u30eb\u30c6\u30a3\u30a8","CITIZEN":"\u30b7\u30c1\u30ba\u30f3","UNIVERSAL":"\u30e6\u30cb\u30d0\u30fc\u30b5\u30eb\u30b8\u30e5\u30cd\u30fc\u30d6","ORIENT":"\u30aa\u30ea\u30a8\u30f3\u30c8","BREITLING":"\u30d6\u30e9\u30a4\u30c8\u30ea\u30f3\u30b0"}

ARTICLES = {
    "IWC": ["242_article_pellaton.txt","244_article_18k_gold.txt","245_article_round_case.txt","246_article_cal89.txt","318_article_iwc_portugieser.txt","319_article_iwc_mk11.txt","320_article_iwc_ingenieur.txt","328_article_iwc_pilot.txt","329_article_iwc_portofino.txt","330_article_iwc_spitfire.txt","331_article_iwc_caliber_table.txt","332_article_iwc_vintage_first.txt"],
    "JLC": ["164_article_triple_calendar.txt","169_article_dirty_dozen.txt","338_article_jlc_deep_sea.txt","339_article_jlc_power_reserve.txt","340_article_jlc_cal478.txt","341_article_jlc_bumper.txt"],
    "LONGINES": ["001_article_conquest_vintage.txt","003_article_ultrachron.txt","333_article_longines_legend_diver.txt","334_article_longines_vintage_first.txt","356_article_longines_wittnauer.txt","357_article_longines_vs_gs.txt"],
    "CARTIER": ["350_article_cartier_pasha.txt","351_article_cartier_movement.txt","359_article_cartier_gold_case.txt","363_article_cartier_ronde.txt","364_article_cartier_ballon.txt"],
    "CITIZEN": ["175_article_chronomaster.txt","176_article_homer.txt","177_article_alarm_watch.txt","178_article_crystal_seven.txt","179_article_ace_jet.txt"],
    "UNIVERSAL": ["342_article_ug_tricompax.txt","343_article_ug_compax.txt","352_article_ug_unimatch.txt","353_article_ug_caliber_table.txt"],
    "ORIENT": ["195_article_royal_orient.txt","196_article_vintage_diver.txt"],
    "BREITLING": ["358_article_breitling_slide_rule.txt"],
}

def escape_html(t):
    return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def extract_title(c):
    for l in c.split("\n"):
        l=l.strip()
        if l.startswith("# "):
            t=l[2:].strip()
            t=re.sub(r'\s*[\uff5c|]\s*FIRE KIDS Magazine\s*$','',t)
            return t
    return "Untitled"

def make_slug(f):
    s=f.replace(".txt","")
    s=re.sub(r'^\d+_article_','',s)
    return s

def extract_faq_pairs(c):
    pairs=[]
    lines=c.split("\n")
    i=0; in_faq=False
    while i<len(lines):
        l=lines[i].strip()
        if re.match(r'^#{1,3}\s+.*(?:\u3088\u304f\u3042\u308b\u8cea\u554f|FAQ)',l):
            in_faq=True; i+=1; continue
        if in_faq and re.match(r'^#{1,3}\s+\u307e\u3068\u3081',l): break
        if in_faq:
            qm=re.match(r'^(?:\*\*)?Q[\uff1a:]?\s*(.+?)(?:\*\*)?$',l)
            if not qm: qm=re.match(r'^#{1,4}\s+Q[\uff1a:]?\s*(.+)$',l)
            if qm:
                q=qm.group(1).strip().rstrip("*")
                al=[]; i+=1
                while i<len(lines):
                    a=lines[i].strip()
                    if a=="" and al: break
                    if a.startswith("**Q") or a.startswith("Q:") or re.match(r'^#{1,4}\s+Q',a): break
                    if re.match(r'^\*?\*?A[\uff1a:]\s*',a):
                        a=re.sub(r'^\*?\*?A[\uff1a:]\s*\*?\*?\s*','',a)
                    if a=="---" or re.match(r'^#{1,3}\s+\u307e\u3068\u3081',a): break
                    if a: al.append(a.strip("*").strip())
                    i+=1
                if al: pairs.append((q," ".join(al)))
                continue
        i+=1
    return pairs

def inline_fmt(t):
    return re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',t)

def fmt_table(rows):
    if not rows: return ""
    hr=[]
    for r in rows:
        cs="".join(f"<td>{inline_fmt(c)}</td>" for c in r)
        hr.append(f"<tr>{cs}</tr>")
    return '<!-- wp:table -->\n<figure class="wp-block-table"><table class="has-fixed-layout"><tbody>\n'+"\n".join(hr)+'\n</tbody></table></figure>\n<!-- /wp:table -->'

def fmt_list(items):
    li="\n".join(f"<li>{inline_fmt(it)}</li>" for it in items)
    return '<!-- wp:list -->\n<ul class="wp-block-list">\n'+li+'\n</ul>\n<!-- /wp:list -->'

def fmt_image(url,alt):
    return f'<!-- wp:image {{"width":"480px","sizeSlug":"large"}} -->\n<figure class="wp-block-image size-large is-resized"><img src="{url}" alt="{escape_html(alt)}" style="width:480px"/></figure>\n<!-- /wp:image -->'

def fmt_cta(link,label):
    return f'<!-- wp:buttons -->\n<div class="wp-block-buttons"><!-- wp:button -->\n<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="{link}">{label}</a></div>\n<!-- /wp:button --></div>\n<!-- /wp:buttons -->'

def body_to_blocks(content,images,brand,cta_link,cta_label):
    lines=content.split("\n"); blocks=[]; i=0
    ip=0; h2c=0; in_tbl=False; trows=[]; in_lst=False; litems=[]; skip=True; cta_done=False
    bjp=BRAND_NAMES_JP[brand]; imgpos={1,3,5}
    while i<len(lines):
        ln=lines[i]; s=ln.strip()
        if skip:
            if s.startswith("# "): skip=False
            elif s=="---" and i>0: skip=False; i+=1; continue
            else: i+=1; continue
        if not s:
            if in_lst and litems: blocks.append(fmt_list(litems)); litems=[]; in_lst=False
            i+=1; continue
        if s.startswith("https://firekids.jp/") or s.startswith("\u2192") or "\u5546\u54c1\u4e00\u89a7\u3092\u898b\u308b" in s or "\u5546\u54c1\u4e00\u89a7\u306f\u3053\u3061\u3089" in s:
            i+=1; continue
        if s=="---":
            if in_lst and litems: blocks.append(fmt_list(litems)); litems=[]; in_lst=False
            i+=1; continue
        if s.startswith("|"):
            if in_lst and litems: blocks.append(fmt_list(litems)); litems=[]; in_lst=False
            if not in_tbl: in_tbl=True; trows=[]
            if re.match(r'^\|[\s\-:|]+\|$',s): i+=1; continue
            cells=[c.strip() for c in s.split("|")[1:-1]]
            trows.append(cells); i+=1; continue
        else:
            if in_tbl and trows: blocks.append(fmt_table(trows)); trows=[]; in_tbl=False
        hm=re.match(r'^(#{1,6})\s+(.+)$',s)
        if hm:
            if in_lst and litems: blocks.append(fmt_list(litems)); litems=[]; in_lst=False
            lv=len(hm.group(1)); ht=hm.group(2).strip()
            if lv==1: i+=1; continue
            if lv==2:
                h2c+=1
                if h2c in imgpos and ip<len(images):
                    blocks.append(fmt_image(images[ip],f"{bjp} {ht}")); ip+=1
                if h2c==4 and not cta_done:
                    blocks.append(fmt_cta(cta_link,cta_label)); cta_done=True
            if lv==2:
                blocks.append(f'<!-- wp:heading -->\n<h2 class="wp-block-heading">{inline_fmt(ht)}</h2>\n<!-- /wp:heading -->')
            else:
                blocks.append(f'<!-- wp:heading {{"level":{lv}}} -->\n<h{lv} class="wp-block-heading">{inline_fmt(ht)}</h{lv}>\n<!-- /wp:heading -->')
            i+=1; continue
        if re.match(r'^[-*]\s+',s):
            in_lst=True; litems.append(re.sub(r'^[-*]\s+','',s)); i+=1; continue
        else:
            if in_lst and litems: blocks.append(fmt_list(litems)); litems=[]; in_lst=False
        blocks.append(f'<!-- wp:paragraph -->\n<p>{inline_fmt(s)}</p>\n<!-- /wp:paragraph -->'); i+=1
    if in_tbl and trows: blocks.append(fmt_table(trows))
    if in_lst and litems: blocks.append(fmt_list(litems))
    while ip<len(images):
        blocks.append(fmt_image(images[ip],f"{bjp} \u30f4\u30a3\u30f3\u30c6\u30fc\u30b8\u30e2\u30c7\u30eb")); ip+=1
    blocks.append(fmt_cta(cta_link,cta_label))
    return "\n\n".join(blocks)

def gen_html(content,brand,txt_fn,idx):
    title=extract_title(content)
    ftitle=f"{title}\uff5cFIRE KIDS Magazine"
    slug=make_slug(txt_fn)
    bjp=BRAND_NAMES_JP[brand]
    cta_link=CTA_LINKS[brand]; cta_label=CTA_LABELS[brand]
    imgs=BRAND_IMAGES[brand]
    off=(idx*3)%len(imgs)
    aimgs=[imgs[(off+j)%len(imgs)] for j in range(3)]
    paras=[]; ph=False
    for l in content.split("\n"):
        ls=l.strip()
        if ls=="---": ph=True; continue
        if not ph: continue
        if ls and not ls.startswith("#") and not ls.startswith("|") and not ls.startswith("-") and not ls.startswith("*") and not ls.startswith("\u2192") and not ls.startswith("https://") and "\u5546\u54c1\u4e00\u89a7" not in ls:
            paras.append(ls.replace("**",""));
            if len(paras)>=2: break
    md=paras[0] if paras else title
    if len(md)>160: md=md[:157]+"..."
    kws=[w for w in re.split(r'[\uff5c|\u30fb\s\u2014\u2500\u2500\u3001]+',title) if len(w)>1][:8]
    kws.extend(["FIRE KIDS","\u30f4\u30a3\u30f3\u30c6\u30fc\u30b8\u6642\u8a08"])
    mkw=", ".join(kws)
    can=f"https://m.firekids.jp/{slug.replace('_','-')}"
    faq=extract_faq_pairs(content)
    fj=""
    if faq:
        fe=[]
        for q,a in faq[:5]:
            fe.append('    {\n      "@type": "Question",\n      "name": "'+escape_html(q)+'",\n      "acceptedAnswer": {\n        "@type": "Answer",\n        "text": "'+escape_html(a)+'"\n      }\n    }')
        fj='\n<!-- wp:html -->\n<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "FAQPage",\n  "mainEntity": [\n'+",\n".join(fe)+'\n  ]\n}\n</script>\n<!-- /wp:html -->'
    od=md[:100] if len(md)>100 else md
    meta=f'<!--\n\u25a0 \u57fa\u672c\u30e1\u30bf\u60c5\u5831\ntitle: {ftitle}\nmeta_description: {md}\nmeta_keywords: {mkw}\ncanonical_url: {can}\n\n\u25a0 Open Graph\uff08SNS\u30b7\u30a7\u30a2\u7528\uff09\nog:title: {ftitle}\nog:description: {od}\nog:type: article\nog:url: {can}\nog:image: {aimgs[0]}\nog:site_name: FIRE KIDS Magazine\nog:locale: ja_JP\n\n\u25a0 Twitter Card\ntwitter:card: summary_large_image\ntwitter:title: {title}\ntwitter:description: {od}\ntwitter:image: {aimgs[0]}\n-->'
    kwj=", ".join('"'+escape_html(k)+'"' for k in kws)
    ajld='<!-- wp:html -->\n<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "Article",\n  "headline": "'+escape_html(title)+'",\n  "description": "'+escape_html(md)+'",\n  "image": "'+aimgs[0]+'",\n  "author": {\n    "@type": "Organization",\n    "name": "FIRE KIDS",\n    "url": "https://firekids.jp/"\n  },\n  "publisher": {\n    "@type": "Organization",\n    "name": "FIRE KIDS Magazine",\n    "url": "https://m.firekids.jp/",\n    "logo": {\n      "@type": "ImageObject",\n      "url": "https://m.firekids.jp/logo.png"\n    }\n  },\n  "datePublished": "2026-03-19",\n  "dateModified": "2026-03-19",\n  "mainEntityOfPage": {\n    "@type": "WebPage",\n    "@id": "'+can+'"\n  },\n  "keywords": ['+kwj+'],\n  "articleSection": "'+bjp+'",\n  "inLanguage": "ja"\n}\n</script>\n<!-- /wp:html -->'
    body=body_to_blocks(content,aimgs,brand,cta_link,cta_label)
    return meta+"\n\n"+ajld+fj+"\n\n"+body

def main():
    gen=[]
    for brand,files in ARTICLES.items():
        bd=os.path.join(BASE,"articles",brand)
        for idx,tf in enumerate(files):
            tp=os.path.join(bd,tf)
            hf=tf.replace(".txt",".html")
            hp=os.path.join(bd,hf)
            if not os.path.exists(tp):
                print(f"SKIP: {brand}/{tf}"); continue
            with open(tp,"r",encoding="utf-8") as f: c=f.read()
            h=gen_html(c,brand,tf,idx)
            with open(hp,"w",encoding="utf-8") as f: f.write(h)
            gen.append(f"{brand}/{hf}")
            print(f"OK: {brand}/{hf}")
    print(f"\nTotal: {len(gen)} HTML files")

if __name__=="__main__": main()
