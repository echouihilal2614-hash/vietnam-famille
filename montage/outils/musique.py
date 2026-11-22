"""Deux musiques provisoires synthétisées (libres de droits) :
 - vacances.wav  : tropical house, 112 BPM, bonne humeur
 - nostalgie.wav : piano lo-fi, 72 BPM, émouvant
Chaque fichier est accompagné d'un .json avec la grille des temps (pour caler les coupes)."""
import numpy as np, soundfile as sf, json
from scipy import signal
SR=48000; rng=np.random.default_rng(3)
import os
OUT=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'musique') + '/'
os.makedirs(OUT, exist_ok=True)
def midi(m): return 440*2**((m-69)/12)
NOTE={'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'F':5,'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11}
def n(s):  # 'A4' -> midi
    name,octv=s[:-1],int(s[-1]); return 12*(octv+1)+NOTE[name]
class Track:
    def __init__(s,dur): s.buf=np.zeros((int(dur*SR)+SR*4,2))
    def add(s,x,at,pan=0.0,gain=1.0):
        i=int(at*SR); 
        if x.ndim==1:
            l=np.cos((pan+1)*np.pi/4); r=np.sin((pan+1)*np.pi/4); x=np.stack([x*l,x*r],1)
        j=min(len(s.buf),i+len(x)); s.buf[i:j]+=x[:j-i]*gain
def tt(d): return np.arange(int(d*SR))/SR
def lp(x,f,o=2): return signal.lfilter(*signal.butter(o,f,fs=SR),x,axis=0)
def hp(x,f,o=2): return signal.lfilter(*signal.butter(o,f,btype='high',fs=SR),x,axis=0)
def bp(x,a,b,o=2): return signal.lfilter(*signal.butter(o,[a,b],btype='band',fs=SR),x,axis=0)
def reverb(x,dur=2.0,mix=0.2,damp=6.0):
    m=int(dur*SR); irL=rng.standard_normal(m)*np.exp(-np.linspace(0,damp,m)); irR=rng.standard_normal(m)*np.exp(-np.linspace(0,damp,m))
    irL=lp(irL,6000); irR=lp(irR,6000); k=np.sqrt(np.sum(irL**2))*4
    wet=np.stack([signal.fftconvolve(x[:,0],irL/k)[:len(x)],signal.fftconvolve(x[:,1],irR/k)[:len(x)]],1)
    return x+wet*mix
def master(x,target_peak=0.89):
    # compression douce + limiteur
    env=np.sqrt(lp(np.mean(x**2,1),8,1).clip(1e-9)); thr=np.percentile(env,90)*0.8
    g=np.where(env>thr,(thr/env)**0.35,1.0); x=x*g[:,None]
    x=np.tanh(x/np.max(np.abs(x))*1.6)/np.tanh(1.6)
    return x/np.max(np.abs(x))*target_peak

# ---------- instruments ----------
def kick(): t=tt(0.45); f=48+110*np.exp(-t*28); return np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-t*7)+0.3*hp(rng.standard_normal(len(t)),3000)*np.exp(-t*300)
def clap():
    t=tt(0.35); x=np.zeros(len(t))
    for d in (0,0.011,0.022): i=int(d*SR); m=len(t)-i; x[i:]+=rng.standard_normal(m)*np.exp(-np.arange(m)/SR*(120 if d<0.02 else 18))
    return bp(x,900,4000)*0.8
def hat(o=False): t=tt(0.25 if o else 0.06); return hp(rng.standard_normal(len(t)),7000)*np.exp(-t*(14 if o else 70))*0.35
def shaker(a=1.0): t=tt(0.07); e=np.sin(np.linspace(0,np.pi,len(t)))**3; return bp(rng.standard_normal(len(t)),5000,11000)*e*0.22*a
def marimba(m,d=0.5,v=1.0):
    t=tt(d+0.3); f=midi(m); I=2.2*np.exp(-t/0.04)
    x=np.sin(2*np.pi*f*t+I*np.sin(2*np.pi*4*f*t))*np.exp(-t/0.32)+0.4*np.sin(2*np.pi*f*t)*np.exp(-t/0.5)
    return x*v*0.35
def bass(m,d):
    t=tt(d); f=midi(m); x=np.sin(2*np.pi*f*t)+0.25*np.sin(2*np.pi*2*f*t)
    e=np.minimum(1,t/0.005)*np.minimum(1,(d-t)/0.03).clip(0); return np.tanh(1.5*x)*e*0.5
def pad(ms,d):
    t=tt(d); x=np.zeros(len(t))
    for m in ms:
        for det in (-0.12,0,0.12): x+=signal.sawtooth(2*np.pi*midi(m+det)*t+rng.uniform(0,6))
    x=lp(x,1800)/ (3*len(ms)); e=np.minimum(1,t/0.25)*np.minimum(1,(d-t)/0.4).clip(0); return x*e*0.5
def flute(m,d):
    t=tt(d); vib=1+0.006*np.sin(2*np.pi*5.2*t)*np.minimum(1,t/0.25); f=midi(m)*vib
    ph=2*np.pi*np.cumsum(f)/SR; x=np.sin(ph)+0.18*np.sin(2*ph)+0.06*np.sin(3*ph)
    x+=bp(rng.standard_normal(len(t)),1500,5000)*0.05
    e=np.minimum(1,t/0.04)*np.minimum(1,(d-t)/0.08).clip(0); return x*e*0.28
def piano(m,d,v=0.8):
    L=d+1.6; t=tt(L); f0=midi(m); x=np.zeros(len(t)); B=0.00035
    for k in range(1,14):
        fk=k*f0*np.sqrt(1+B*k*k)
        if fk>16000: break
        a=(v**(0.6+0.15*k))/k**1.1; tau=(3.2 if m<60 else 2.2)/(1+0.35*k)
        for det in (1.0,1.0006): x+=a*np.sin(2*np.pi*fk*det*t+rng.uniform(0,6))*np.exp(-t/tau)*0.5
    x+=lp(rng.standard_normal(len(t)),3000)*np.exp(-t*80)*0.05*v
    rel=np.ones(len(t)); i=int(d*SR); r=np.exp(-np.arange(len(t)-i)/SR*5); rel[i:]=r
    return x*rel*np.minimum(1,t/0.002)*0.22

# ---------- 1) VACANCES : 112 BPM ----------
def vacances():
    bpm=112; b=60/bpm; bar=4*b; bars=32; T=Track(bars*bar+2)
    prog=[('A',['A3','C#4','E4'],'A1'),('E',['G#3','B3','E4'],'E2'),('F#m',['A3','C#4','F#4'],'F#1'),('D',['A3','D4','F#4'],'D2')]
    pluck_rhythm=[0,0.75,1.5,2.5,3,3.5]   # motif syncopé 3-3-2
    melody=[('E5',0,0.75),('C#5',0.75,0.75),('E5',1.5,1),('F#5',2.5,0.5),('E5',3,1),
            ('B4',4,0.75),('C#5',4.75,0.75),('E5',5.5,1.5),('C#5',7,1),
            ('A4',8,0.75),('C#5',8.75,0.75),('F#5',9.5,1),('E5',10.5,1.5),
            ('D5',12,0.75),('C#5',12.75,0.75),('B4',13.5,1),('A4',14.5,1.5)]
    sections={'intro':(0,8),'montee':(8,12),'drop1':(12,20),'pont':(20,24),'drop2':(24,32)}
    def sec(i):
        for k,(a,z) in sections.items():
            if a<=i<z: return k
    side=np.ones(len(T.buf))
    for i in range(bars):
        s=sec(i); t0=i*bar; name,ch,root=prog[i%4]
        full = s in ('drop1','drop2')
        # plucks
        for p in pluck_rhythm:
            for j,nn in enumerate(ch): T.add(marimba(n(nn)+12,0.4,0.9 if p in (0,1.5,3) else 0.7),t0+p*b,pan=(-0.4,0,0.4)[j],gain=0.9 if s!='intro' else 0.6)
        # pad
        T.add(pad([n(x) for x in ch],bar),t0,gain=0.32 if full else 0.25)
        if s in ('montee','drop1','drop2','pont'):
            for k in range(8): T.add(shaker(1.0 if k%2 else 0.6),t0+k*b/2,pan=0.3)
        if full or s=='pont':
            for k in range(4): T.add(kick(),t0+k*b,gain=0.9); side_i=int((t0+k*b)*SR); m=int(0.25*SR); side[side_i:side_i+m]=np.minimum(side[side_i:side_i+m],0.35+0.65*np.linspace(0,1,m)**0.7)
        if full:
            for k in (1,3): T.add(clap(),t0+k*b,gain=0.7)
            for k in range(4): T.add(hat(k==3),t0+k*b+b/2,pan=-0.2)
            for p,d in [(0,0.7),(0.75,0.7),(1.5,1),(2.5,0.45),(3,0.9)]: T.add(bass(n(root)+12,d*b),t0+p*b,gain=0.9)
            mi=(i-(12 if s=='drop1' else 24))%4
            for nn,st,du in melody:
                if mi*4<=st<mi*4+4: T.add(flute(n(nn),du*b*0.95),t0+(st-mi*4)*b,pan=0.1,gain=0.8)
        if s=='montee':
            for k in range(8 if i<11 else 16): T.add(kick()*0.6 if i<11 else clap()*0.7,t0+k*(b/2 if i<11 else b/4))
        if s=='intro' and i>=4:
            for k in range(4): T.add(kick()*0.5,t0+k*b)
    # riser vers le drop 1
    d=4*bar; t=tt(d); r=bp(rng.standard_normal(len(t)),600,9000)*(t/d)**2*0.35
    T.add(r,8*bar,gain=1.0)
    x=T.buf; x=x*side[:,None]**0.6
    x=reverb(x,1.6,0.18); x=hp(x,32); x=master(x)
    end=int((bars*bar+1.5)*SR); x=x[:end]; fade=int(1.5*SR); x[-fade:]*=np.linspace(1,0,fade)[:,None]
    sf.write(OUT+'vacances.wav',x,SR,subtype='PCM_24')
    json.dump({'bpm':bpm,'temps':[round(k*b,4) for k in range(bars*4+1)],'mesures':[round(k*bar,4) for k in range(bars+1)],
               'sections':{k:[round(a*bar,3),round(z*bar,3)] for k,(a,z) in sections.items()},'duree':round(len(x)/SR,3)},open(OUT+'vacances.json','w'),indent=1)

# ---------- 2) NOSTALGIE : 72 BPM ----------
def nostalgie():
    bpm=72; b=60/bpm; bar=4*b; bars=16; T=Track(bars*bar+4)
    prog=[(['D3','A3','E4','F#4'],'D2'),(['C#3','A3','E4','G#4'],'A1'),(['B2','F#3','D4','A4'],'B1'),(['G2','D3','B3','F#4'],'G1')]
    mel=[('F#5',0,1.5),('E5',1.5,0.5),('D5',2,2),('E5',4,1.5),('C#5',5.5,0.5),('A4',6,2),('B4',8,1),('C#5',9,1),('D5',10,1.5),('F#5',11.5,0.5),('E5',12,4)]
    for i in range(bars):
        t0=i*bar; ch,root=prog[i%4]
        T.add(piano(n(root)+12,bar*0.98,0.55),t0,pan=-0.2)
        arp=[ch[0],ch[1],ch[2],ch[3],ch[2],ch[1],ch[2],ch[3]]
        for k,nn in enumerate(arp): T.add(piano(n(nn),b*0.9,0.42 if k%2 else 0.5),t0+k*b/2,pan=-0.1+0.05*(k%4))
        if i>=4:
            T.add(pad([n(x)+12 for x in ch[1:]],bar),t0,gain=0.18 if i<12 else 0.28)
            st=(i%4)*4
            for nn,s0,du in mel:
                if st<=s0<st+4: T.add(piano(n(nn),du*b,0.62),t0+(s0-st)*b,pan=0.2)
    x=reverb(T.buf,3.0,0.35,damp=5)
    # lo-fi : coupe des aigus + léger pleurage
    x=lp(x,6500); w=1+0.0018*np.sin(2*np.pi*0.55*np.arange(len(x))/SR)
    idx=np.cumsum(w); idx=idx[idx<len(x)-1]; x=np.stack([np.interp(idx,np.arange(len(x)),x[:,c]) for c in range(2)],1)
    # craquements de vinyle
    m=len(x); cr=np.zeros(m); k=rng.choice(m,int(m/SR*25),replace=False); cr[k]=rng.standard_normal(len(k))
    cr=bp(cr,1000,8000)*0.05; x=x+np.stack([cr,np.roll(cr,40)],1)+hp(rng.standard_normal((m,2)),3000)*0.002
    x=hp(x,45); x=master(x,0.85)
    end=int((bars*bar+3.5)*SR); x=x[:end]; fade=int(3.5*SR); x[-fade:]*=np.linspace(1,0,fade)[:,None]**1.5
    sf.write(OUT+'nostalgie.wav',x,SR,subtype='PCM_24')
    json.dump({'bpm':bpm,'temps':[round(k*b,4) for k in range(bars*4+1)],'mesures':[round(k*bar,4) for k in range(bars+1)],'duree':round(len(x)/SR,3)},open(OUT+'nostalgie.json','w'),indent=1)
vacances(); nostalgie(); print('ok')
