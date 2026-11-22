"""Inventaire des rushes : métadonnées (date, GPS -> lieu du voyage, orientation, HDR),
planches contact pour visionner chaque vidéo, et pics sonores (rires, cris...).
Usage : python3 analyse.py <dossier_rushes> <dossier_sortie>"""
import sys, os, json, subprocess, re, math, datetime as dt
from PIL import Image, ImageDraw, ImageFont, ImageOps
import numpy as np
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception: pass
ATELIER=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOPS=json.load(open(ATELIER+'/carte.json'))['stops']
VID=('.mov','.mp4','.m4v','.avi','.mkv','.3gp','.mts','.webm')
IMG=('.jpg','.jpeg','.png','.heic','.heif','.webp','.dng')
FONT=ImageFont.truetype(ATELIER+'/fonts/Montserrat_600SemiBold.ttf',22)
FONTB=ImageFont.truetype(ATELIER+'/fonts/Montserrat_800ExtraBold.ttf',30)

def run(cmd): return subprocess.run(cmd,capture_output=True,text=True)
def lieu(lat,lon):
    if lat is None: return None,None
    best=min(STOPS,key=lambda s:(s['lat']-lat)**2+((s['lon']-lon)*math.cos(math.radians(lat)))**2)
    d=math.hypot(best['lat']-lat,(best['lon']-lon)*math.cos(math.radians(lat)))*111
    return best['id'],round(d,1)
def iso6709(s):
    m=re.match(r'([+-]\d+\.?\d*)([+-]\d+\.?\d*)',s or '')
    return (float(m.group(1)),float(m.group(2))) if m else (None,None)

def info_video(p):
    j=json.loads(run(['ffprobe','-v','error','-print_format','json','-show_format','-show_streams',p]).stdout or '{}')
    v=next((s for s in j.get('streams',[]) if s['codec_type']=='video'),None)
    a=next((s for s in j.get('streams',[]) if s['codec_type']=='audio'),None)
    if not v: return None
    tags={k.lower():val for k,val in {**j['format'].get('tags',{}),**v.get('tags',{})}.items()}
    rot=0
    for sd in v.get('side_data_list',[]):
        if 'rotation' in sd: rot=int(sd['rotation'])
    w,h=v['width'],v['height']
    if abs(rot)%180==90: w,h=h,w
    date=tags.get('com.apple.quicktime.creationdate') or tags.get('creation_time')
    lat,lon=iso6709(tags.get('com.apple.quicktime.location.iso6709') or tags.get('location'))
    fr=v.get('avg_frame_rate','0/1'); num,den=map(int,fr.split('/')); fps=round(num/den,2) if den else 0
    return dict(type='video',duree=round(float(j['format'].get('duration',0)),2),w=w,h=h,fps=fps,
        codec=v['codec_name'],hdr=v.get('color_transfer') in ('arib-std-b67','smpte2084'),transfer=v.get('color_transfer'),
        son=bool(a),date=date,lat=lat,lon=lon,appareil=(tags.get('com.apple.quicktime.model') or tags.get('com.android.manufacturer') or ''),
        ralenti=fps>=100)

def info_photo(p):
    im=Image.open(p); ex=im.getexif(); w,h=im.size
    o=ex.get(274,1); 
    if o in (5,6,7,8): w,h=h,w
    date=None; lat=lon=None
    try:
        sub=ex.get_ifd(0x8769); date=sub.get(36867) or ex.get(306)
    except Exception: date=ex.get(306)
    try:
        g=ex.get_ifd(0x8825)
        if g and 2 in g:
            f=lambda v:float(v[0])+float(v[1])/60+float(v[2])/3600
            lat=f(g[2])*(-1 if g.get(1)=='S' else 1); lon=f(g[4])*(-1 if g.get(3)=='W' else 1)
    except Exception: pass
    if date: date=date.replace(':','-',2).replace(' ','T')
    return dict(type='photo',w=w,h=h,date=date,lat=lat,lon=lon,appareil=str(ex.get(272,'')))

def planche_video(p,info,out):
    d=info['duree']; n=12 if d>8 else max(4,int(d/0.75))
    cols=4; rows=math.ceil(n/cols); tw=400; th=int(tw*info['h']/info['w']) if info['w'] else 225
    th=min(th,400); tw=int(th*info['w']/info['h']) if th==400 else tw
    sheet=Image.new('RGB',(cols*tw+(cols+1)*8,rows*th+(rows+1)*8+50),(20,20,24)); dr=ImageDraw.Draw(sheet)
    dr.text((10,10),f"{os.path.basename(p)}  ·  {d:.1f}s  ·  {info['w']}x{info['h']}  {info['fps']}fps{'  HDR' if info['hdr'] else ''}{'  RALENTI' if info['ralenti'] else ''}",font=FONT,fill=(255,255,255))
    tm='zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=rgb24,' if info['hdr'] else ''
    for i in range(n):
        t=(i+0.5)*d/n
        r=subprocess.run(['ffmpeg','-v','error','-ss',f'{t:.3f}','-i',p,'-frames:v','1','-vf',f'{tm}scale={tw}:{th}','-f','image2pipe','-vcodec','png','-'],capture_output=True)
        if not r.stdout: continue
        import io; im=Image.open(io.BytesIO(r.stdout)).convert('RGB')
        x=8+(i%cols)*(tw+8); y=58+(i//cols)*(th+8); sheet.paste(im,(x,y))
        dr.rectangle([x,y,x+78,y+30],fill=(0,0,0)); dr.text((x+6,y+3),f'{t:5.1f}s',font=FONT,fill=(255,220,80))
    sheet.save(out,quality=85)

def pics_sonores(p,duree):
    """Repère les moments où le son monte d'un coup (rires, cris, applaudissements)."""
    r=subprocess.run(['ffmpeg','-v','error','-i',p,'-vn','-ac','1','-ar','8000','-f','s16le','-'],capture_output=True)
    x=np.frombuffer(r.stdout,dtype=np.int16).astype(np.float32)/32768
    if len(x)<8000: return []
    hop=800; rms=np.sqrt(np.convolve(x**2,np.ones(hop)/hop,'same')[::hop]+1e-9); db=20*np.log10(rms)
    base=np.percentile(db,50); pics=[]
    for i in range(len(db)):
        if db[i]>base+12 and db[i]==db[max(0,i-10):i+10].max(): pics.append(round(i*hop/8000,1))
    return pics[:10]

def planche_photos(items,out,dossier):
    tw=300; cols=6; rows=math.ceil(len(items)/cols)
    sheet=Image.new('RGB',(cols*(tw+8)+8,rows*(tw+40)+8),(20,20,24)); dr=ImageDraw.Draw(sheet)
    for k,(nom,inf) in enumerate(items):
        try: im=ImageOps.exif_transpose(Image.open(os.path.join(dossier,nom))).convert('RGB'); im.thumbnail((tw,tw))
        except Exception: continue
        x=8+(k%cols)*(tw+8); y=8+(k//cols)*(tw+40); sheet.paste(im,(x+(tw-im.width)//2,y+(tw-im.height)//2))
        dr.text((x,y+tw+6),nom[:28],font=ImageFont.truetype(ATELIER+'/fonts/Montserrat_600SemiBold.ttf',16),fill=(255,255,255))
    sheet.save(out,quality=85)

if __name__=='__main__':
    src,dst=sys.argv[1],sys.argv[2]; os.makedirs(dst+'/planches',exist_ok=True)
    inv={}
    for root,_,files in os.walk(src):
        for f in sorted(files):
            p=os.path.join(root,f); rel=os.path.relpath(p,src); ext=os.path.splitext(f)[1].lower()
            try:
                if ext in VID:
                    i=info_video(p)
                    if not i: continue
                    planche_video(p,i,f"{dst}/planches/{rel.replace('/','__')}.jpg")
                    i['pics_son']=pics_sonores(p,i['duree']) if i['son'] else []
                elif ext in IMG: i=info_photo(p)
                else: continue
            except Exception as e:
                print('!!',rel,e); continue
            i['lieu'],i['dist_km']=lieu(i['lat'],i['lon']); inv[rel]=i; print('ok',rel,i.get('date'),i['lieu'])
    json.dump(inv,open(dst+'/inventaire.json','w'),indent=1,ensure_ascii=False)
    photos=sorted([(k,v) for k,v in inv.items() if v['type']=='photo'],key=lambda kv:kv[1]['date'] or '')
    for b in range(0,len(photos),36): planche_photos(photos[b:b+36],f"{dst}/planches/_photos_{b//36+1:02d}.jpg",src)
    # résumé chronologique
    rows=sorted(inv.items(),key=lambda kv:kv[1]['date'] or 'z')
    with open(dst+'/inventaire.md','w') as fh:
        fh.write('| fichier | type | date | lieu | durée | format | notes |\n|---|---|---|---|---|---|---|\n')
        for k,v in rows:
            notes=' '.join(x for x in ['HDR' if v.get('hdr') else '','ralenti' if v.get('ralenti') else '',('pics son: '+','.join(map(str,v.get('pics_son',[])))) if v.get('pics_son') else ''] if x)
            fh.write(f"| {k} | {v['type']} | {(v['date'] or '?')[:16]} | {v['lieu'] or '?'} | {v.get('duree','')} | {v['w']}x{v['h']} | {notes} |\n")
    print(len(inv),'fichiers')
