"""Banque d'effets sonores synthétisés (libres de droits) pour le montage."""
import numpy as np, soundfile as sf
from scipy import signal
SR = 48000
rng = np.random.default_rng(7)
import os
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sons') + '/'

def t(d): return np.arange(int(d*SR))/SR
def norm(x, peak=0.9): return x/np.max(np.abs(x)+1e-9)*peak
def env_adsr(n, a, r, curve=2.0):
    e = np.ones(n); na=int(a*SR); nr=int(r*SR)
    if na: e[:na] = np.linspace(0,1,na)**curve
    if nr: e[-nr:] = np.linspace(1,0,nr)**curve
    return e
def bp_sweep(x, f0, f1, q=2.0, steps=64):
    """Filtre passe-bande dont la fréquence glisse de f0 à f1 (par blocs)."""
    out = np.zeros_like(x); n=len(x); blk=n//steps
    zi=None
    for i in range(steps):
        f = f0*(f1/f0)**(i/(steps-1))
        b,a = signal.iirpeak(min(f, SR/2*0.95), q, fs=SR)
        seg = x[i*blk:(i+1)*blk if i<steps-1 else n]
        if zi is None: zi = signal.lfilter_zi(b,a)*0
        y, zi = signal.lfilter(b,a,seg,zi=zi)
        out[i*blk:i*blk+len(y)] = y
    return out
def stereo(x, pan_from=0.0, pan_to=0.0):
    p = np.linspace(pan_from, pan_to, len(x))
    l = x*np.cos((p+1)*np.pi/4); r = x*np.sin((p+1)*np.pi/4)
    return np.stack([l,r],1)
def reverb(x, dur=1.2, mix=0.25):
    n=int(dur*SR); ir = rng.standard_normal(n)*np.exp(-np.linspace(0,7,n)); ir/=np.sum(np.abs(ir))/8
    if x.ndim==1: x=np.stack([x,x],1)
    y = np.stack([signal.fftconvolve(x[:,c], ir*(1 if c==0 else np.roll(ir,97)))[:len(x)] for c in range(2)],1)
    return x*(1-mix)+y*mix
def save(name, x, peak=0.9):
    if x.ndim==1: x=np.stack([x,x],1)
    sf.write(OUT+name+'.wav', norm(x,peak), SR, subtype='PCM_24')

# --- whoosh court / long (passage de transition) ---
for name,d,f0,f1,pf,pt in [('whoosh',0.55,300,4000,-0.8,0.8),('whoosh_long',1.1,200,5000,-0.9,0.9),('whoosh_inverse',0.6,4000,300,0.8,-0.8)]:
    n=int(d*SR); x=rng.standard_normal(n)
    y=bp_sweep(x,f0,f1,q=1.4)
    e=np.sin(np.linspace(0,np.pi,n))**2.5
    save(name, reverb(stereo(y*e,pf,pt),0.6,0.2))
# --- riser (montée avant un drop) ---
d=2.5; n=int(d*SR); tt=t(d)
noise=bp_sweep(rng.standard_normal(n),400,9000,q=1.0)
tone=signal.chirp(tt,120,d,900,method='logarithmic')*0.25
e=np.linspace(0,1,n)**2.2; e[-int(0.03*SR):]*=np.linspace(1,0,int(0.03*SR))
save('riser', reverb(stereo((noise+tone)*e),1.5,0.3))
# --- impact / boom ---
d=1.8; tt=t(d)
sub=np.sin(2*np.pi*(55*tt+ (90/6)*(1-np.exp(-6*tt))))*np.exp(-2.8*tt)
crack=rng.standard_normal(len(tt))*np.exp(-30*tt)
b,a=signal.butter(2,3000,fs=SR); crack=signal.lfilter(b,a,crack)
save('impact', reverb(sub+0.6*crack,1.6,0.25), 0.95)
# --- pop (apparition de texte / emoji) ---
d=0.12; tt=t(d); f=900*np.exp(-25*tt)+300
x=np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-30*tt)
save('pop', x)
# --- déclencheur appareil photo ---
d=0.35; x=np.zeros(int(d*SR))
for start,amp in [(0.0,1.0),(0.11,0.7)]:
    i=int(start*SR); m=int(0.05*SR); tt=t(0.05)
    click=rng.standard_normal(m)*np.exp(-90*tt)*amp
    b,a=signal.butter(2,[1500,9000],btype='band',fs=SR); x[i:i+m]+=signal.lfilter(b,a,click)
    x[i:i+m]+=np.sin(2*np.pi*180*tt)*np.exp(-60*tt)*0.4*amp
save('declic_photo', reverb(x,0.4,0.15))
# --- scratch de vinyle (moment gênant / arrêt sur image) ---
d=0.7; tt=t(d)
pos = 0.004*np.sin(2*np.pi*3.2*tt)*np.exp(-1.2*tt) + 0.002*np.sin(2*np.pi*7.5*tt)
speed=np.gradient(pos)*SR
src=signal.lfilter(*signal.butter(2,[400,5000],btype='band',fs=SR), rng.standard_normal(SR*2))
ph=np.cumsum(np.abs(speed))*40; ph=np.clip(ph,0,len(src)-2)
x=np.interp(ph,np.arange(len(src)),src)*np.clip(np.abs(speed)*80,0,1)
x+=0.5*np.sin(2*np.pi*np.cumsum(200+np.abs(speed)*4000)/SR)*np.clip(np.abs(speed)*60,0,1)
save('scratch', x*env_adsr(len(x),0.005,0.1))
# --- arrêt de cassette (tape stop) ---
d=0.9; tt=t(d); f=np.linspace(1,0,len(tt))**1.5
x=signal.sawtooth(2*np.pi*np.cumsum(220*f)/SR)*0.3+signal.sawtooth(2*np.pi*np.cumsum(330*f)/SR)*0.2
x=signal.lfilter(*signal.butter(2,1800,fs=SR),x)*f
save('tape_stop', x)
# --- rembobinage VHS ---
d=1.6; tt=t(d)
f=2500+1500*np.sin(2*np.pi*11*tt)+800*np.sin(2*np.pi*2.3*tt)
whine=np.sin(2*np.pi*np.cumsum(f)/SR)*0.25
hiss=signal.lfilter(*signal.butter(2,3000,btype='high',fs=SR),rng.standard_normal(len(tt)))*0.35
mech=(np.sin(2*np.pi*31*tt)>0.95)*rng.standard_normal(len(tt))*0.3
save('rembobinage_vhs', (whine+hiss+mech)*env_adsr(len(tt),0.08,0.15), 0.7)
# --- glitch numérique ---
d=0.45; x=np.zeros(int(d*SR)); i=0
while i<len(x):
    m=int(rng.uniform(0.008,0.04)*SR); kind=rng.integers(3); tt=np.arange(m)/SR
    seg = signal.square(2*np.pi*rng.uniform(80,1200)*tt) if kind==0 else (rng.standard_normal(m) if kind==1 else np.zeros(m))
    x[i:i+m]=seg[:len(x[i:i+m])]*rng.uniform(0.3,1); i+=m
save('glitch', stereo(x,-0.5,0.5), 0.6)
# --- ding (cloche, moment drôle) ---
d=1.5; tt=t(d); x=sum(a*np.sin(2*np.pi*f*tt)*np.exp(-k*tt) for f,a,k in [(1318,1,3),(2637,0.5,5),(3950,0.25,8),(1975,0.3,4)])
save('ding', reverb(x,1.0,0.2), 0.7)
# --- boing (cartoon) ---
d=0.8; tt=t(d); f=300+180*np.sin(2*np.pi*14*tt)*np.exp(-3*tt)+200*np.exp(-4*tt)
save('boing', np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-3.5*tt))
# --- craquement de vinyle (fond nostalgique, boucle 20 s) ---
d=20; n=int(d*SR); x=np.zeros(n)
idx=rng.choice(n, 900, replace=False); x[idx]=rng.standard_normal(900)*rng.uniform(0.2,1,900)
x=signal.lfilter(*signal.butter(2,[800,9000],btype='band',fs=SR),x)
hiss=signal.lfilter(*signal.butter(2,[2000,12000],btype='band',fs=SR),rng.standard_normal(n))*0.012
rumble=signal.lfilter(*signal.butter(2,60,fs=SR),rng.standard_normal(n))*0.15
save('vinyle_fond', x+hiss+rumble, 0.9)
# --- projecteur 8mm (fond nostalgique, boucle 20 s) ---
tt=t(20); clicks=np.zeros(len(tt)); step=int(SR/18)
for k in range(0,len(tt)-200,step): clicks[k:k+120]+=rng.standard_normal(120)*np.exp(-np.arange(120)/25)
clicks=signal.lfilter(*signal.butter(2,[1000,6000],btype='band',fs=SR),clicks)
motor=0.15*np.sin(2*np.pi*60*tt)+0.08*np.sin(2*np.pi*120*tt)
save('projecteur_fond', clicks+motor*0.3, 0.9)
print('ok')

# ================= bruits de tournage / photo =================
# --- clap de cinéma (claquement sec en bois) ---
d=0.5; tt=t(d); x=rng.standard_normal(len(tt))*np.exp(-tt*60)
x=signal.lfilter(*signal.butter(2,[700,6000],btype='band',fs=SR),x)
x+=0.6*np.sin(2*np.pi*420*tt)*np.exp(-tt*45)+0.3*np.sin(2*np.pi*1150*tt)*np.exp(-tt*70)
save('clap_cinema', reverb(x,0.5,0.18), 0.95)
# --- bip REC de caméscope (deux bips) ---
x=np.zeros(int(0.45*SR))
for st in (0.0,0.18):
    i=int(st*SR); m=int(0.09*SR); tt=np.arange(m)/SR
    x[i:i+m]+=np.sin(2*np.pi*2400*tt)*np.minimum(1,np.minimum(tt,(m/SR-tt))/0.004)
save('bip_rec', x, 0.5)
# --- flash qui se charge puis se déclenche ---
d=1.4; tt=t(d); f=900+3200*(tt/d)**0.6
x=np.sin(2*np.pi*np.cumsum(f)/SR)*0.25*np.minimum(1,tt/0.05)
x[int(1.15*SR):]=0
i=int(1.15*SR); m=len(x)-i; tp=np.arange(m)/SR
x[i:]+=signal.lfilter(*signal.butter(2,[1200,9000],btype='band',fs=SR),rng.standard_normal(m))*np.exp(-tp*70)
x[i:]+=0.5*np.sin(2*np.pi*160*tp)*np.exp(-tp*40)
save('flash', reverb(x,0.4,0.15), 0.8)
# --- avance de pellicule (molette à cliquets) ---
d=0.7; x=np.zeros(int(d*SR))
for k in range(9):
    i=int((0.02+k*0.068+rng.uniform(-0.006,0.006))*SR); m=int(0.03*SR); tp=np.arange(m)/SR
    x[i:i+m]+=signal.lfilter(*signal.butter(2,[1800,7000],btype='band',fs=SR),rng.standard_normal(m))*np.exp(-tp*220)*rng.uniform(0.6,1)
save('avance_pellicule', x, 0.7)
# --- Polaroid qui éjecte la photo (moteur + engrenages) ---
d=1.3; tt=t(d); env=np.minimum(1,tt/0.06)*np.minimum(1,(d-tt)/0.1).clip(0)
motor=signal.sawtooth(2*np.pi*np.cumsum(95+25*np.sin(2*np.pi*3*tt))/SR)*0.35
gear=signal.lfilter(*signal.butter(2,[2000,6000],btype='band',fs=SR),rng.standard_normal(len(tt)))*(0.5+0.5*np.sign(np.sin(2*np.pi*38*tt)))*0.25
x=signal.lfilter(*signal.butter(2,2500,fs=SR),motor)+gear
save('polaroid', x*env, 0.6)
# --- rafale de photos (paparazzi) ---
d=1.2; x=np.zeros(int(d*SR)); sh,_=sf.read(OUT+'declic_photo.wav')
sh=sh[:,0] if sh.ndim>1 else sh
for k in range(7):
    i=int(k*0.15*SR); j=min(len(x),i+len(sh)); x[i:j]+=sh[:j-i]*rng.uniform(0.6,1)
save('rafale_photos', x, 0.85)
# --- démarrage de projecteur (moteur qui prend de la vitesse) ---
d=2.0; tt=t(d); rate=4+14*np.minimum(1,tt/1.4)**1.5; ph=np.cumsum(rate)/SR
clicks=np.zeros(len(tt)); idx=np.where(np.diff(np.floor(ph))>0)[0]
for i in idx: clicks[i:i+120]+=rng.standard_normal(min(120,len(tt)-i))*np.exp(-np.arange(min(120,len(tt)-i))/25)
clicks=signal.lfilter(*signal.butter(2,[1000,6000],btype='band',fs=SR),clicks)
hum=0.12*np.sin(2*np.pi*np.cumsum(20+40*np.minimum(1,tt/1.4))/SR)
save('projecteur_demarrage', clicks+hum, 0.6)
print('bruits de tournage ok')
