"""Free game alerts for Discord.

Checks Epic Games' own free-games feed and GamerPower's public giveaway feed (Steam, GOG), and posts each new
free game once to a Discord webhook. Only full games that are free to keep right now are posted: no DLC, loot,
betas, or "free weekend" trials. Posted games are remembered in state.json (saved between runs by the workflow
cache), so nothing is posted twice.
"""
import datetime as dt, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

EPIC_URL='https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US'
GAMERPOWER_URL='https://www.gamerpower.com/api/giveaways'
GAMERPOWER_PLATFORMS=('steam','gog')          # Epic comes straight from Epic
STATE_PATH=Path(os.environ.get('STATE_PATH','.state/state.json'))
UA={'User-Agent':'free-game-alerts/1.0 (Discord bot; github.com/WhiskeyGinger/free-game-alerts)','Accept':'application/json'}
STORE_ICON={'Epic Games':'🟣','Steam':'🔵','GOG':'🟪'}
COLOR=5763719
CT_OFFSETS={True:-5,False:-6}

def get_json(url, opener=urllib.request.urlopen, attempts=3, sleep=time.sleep):
    for a in range(attempts):
        try:
            with opener(urllib.request.Request(url,headers=UA),timeout=30) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429,500,502,503,504) or a==attempts-1: raise
        except (urllib.error.URLError,TimeoutError):
            if a==attempts-1: raise
        sleep(2**(a+1))

def parse_time(s):
    if not s or s in ('N/A','n/a'): return None
    s=str(s).strip().replace('Z','+00:00')
    for fmt in (None,'%Y-%m-%d %H:%M:%S'):
        try:
            d=dt.datetime.fromisoformat(s) if fmt is None else dt.datetime.strptime(s,fmt)
            return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
        except ValueError: continue
    return None

def key(title):
    """Comparison key so the same game from two feeds is posted once."""
    return re.sub(r'[^a-z0-9]','',re.sub(r'\b(free|giveaway|steam|gog|epic games?|key|pc)\b','',str(title).lower()))

# --- sources --------------------------------------------------------------------------------------------------------
def epic_games(data, now):
    """Games Epic is giving away right now (100% off, promotion window open)."""
    out=[]
    for e in ((data or {}).get('data') or {}).get('Catalog',{}).get('searchStore',{}).get('elements',[]) or []:
        try:
            promos=(e.get('promotions') or {}).get('promotionalOffers') or []
            offers=[o for p in promos for o in (p.get('promotionalOffers') or [])]
            live=[o for o in offers if (o.get('discountSetting') or {}).get('discountPercentage')==0
                  and parse_time(o.get('startDate')) and parse_time(o.get('endDate')) and parse_time(o['startDate'])<=now<parse_time(o['endDate'])]
            if not live: continue
            if (e.get('offerType') or 'BASE_GAME') not in ('BASE_GAME','BUNDLE','OTHERS'): continue
            price=((e.get('price') or {}).get('totalPrice') or {})
            fmt=(price.get('fmtPrice') or {}).get('originalPrice')
            slug=None
            for m in (e.get('catalogNs') or {}).get('mappings') or []:
                if m.get('pageSlug'): slug=m['pageSlug']; break
            slug=slug or e.get('productSlug') or e.get('urlSlug')
            url='https://store.epicgames.com/en-US/p/'+slug.split('/')[0] if slug else 'https://store.epicgames.com/en-US/free-games'
            img=next((i.get('url') for i in e.get('keyImages') or [] if i.get('type') in ('OfferImageWide','DieselStoreFrontWide','Thumbnail')),None)
            out.append({'id':'epic:'+str(e.get('id')),'title':e.get('title'),'store':'Epic Games','worth':fmt if fmt and fmt!='0' else None,
                        'ends':parse_time(live[0]['endDate']),'url':url,'image':img})
        except (KeyError,TypeError,AttributeError,IndexError): continue
    return out

def gamerpower_games(items, now):
    """Full games free to keep on Steam/GOG (GamerPower type 'game', status active)."""
    out=[]
    for g in items if isinstance(items,list) else []:
        try:
            if g.get('type')!='Game' or str(g.get('status','')).lower()!='active': continue
            plats=str(g.get('platforms',''))
            store='Steam' if 'Steam' in plats else 'GOG' if 'GOG' in plats else None
            if not store: continue
            ends=parse_time(g.get('end_date'))
            if ends and ends<=now: continue
            worth=g.get('worth') if g.get('worth') not in (None,'N/A','$0.00') else None
            title=re.sub(r'\s*\((Steam|GOG|PC)\)\s*Giveaway\s*$','',str(g.get('title','')),flags=re.I).strip()
            out.append({'id':'gp:'+str(g.get('id')),'title':title,'store':store,'worth':worth,'ends':ends,
                        'url':g.get('open_giveaway_url') or g.get('gamerpower_url'),'image':g.get('image') or g.get('thumbnail')})
        except (KeyError,TypeError,AttributeError): continue
    return out

def collect(now, get=get_json):
    games=[]; errors=[]
    try: games+=epic_games(get(EPIC_URL),now)
    except Exception as e: errors.append('Epic: %s'%type(e).__name__)
    for p in GAMERPOWER_PLATFORMS:
        try: games+=gamerpower_games(get(GAMERPOWER_URL+'?'+urllib.parse.urlencode({'platform':p,'type':'game'})),now)
        except Exception as e: errors.append('GamerPower %s: %s'%(p,type(e).__name__))
    seen=set(); unique=[]
    for g in games:
        k=(key(g['title']),g['store'])
        if not g.get('title') or k in seen: continue
        seen.add(k); unique.append(g)
    return unique,errors

# --- state ----------------------------------------------------------------------------------------------------------
def load_state(path=STATE_PATH):
    try: d=json.loads(Path(path).read_text()); return d if isinstance(d,dict) else {}
    except (OSError,ValueError): return {}
def save_state(state, now, path=STATE_PATH, keep_days=60):
    cutoff=(now-dt.timedelta(days=keep_days)).isoformat()
    state={k:v for k,v in state.items() if v>=cutoff}
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text(json.dumps(state,indent=1,sort_keys=True))
def state_key(g): return '%s|%s|%s'%(g['store'],key(g['title']),g['ends'].date().isoformat() if g.get('ends') else '')

# --- messages -------------------------------------------------------------------------------------------------------
def central(t):
    """US Central time label (CST/CDT by the US rule: 2nd Sunday of March to 1st Sunday of November, 2 am local)."""
    y=t.year
    def nth_sunday(month,n):
        d=dt.date(y,month,1); d+=dt.timedelta(days=(6-d.weekday())%7); return d+dt.timedelta(weeks=n-1)
    start=dt.datetime.combine(nth_sunday(3,2),dt.time(8),tzinfo=dt.timezone.utc)
    end=dt.datetime.combine(nth_sunday(11,1),dt.time(7),tzinfo=dt.timezone.utc)
    dst=start<=t<end; local=t+dt.timedelta(hours=CT_OFFSETS[dst])
    return local.strftime('%a %b ')+str(local.day)+local.strftime(', %I:%M %p ').replace(' 0',' ')+('CDT' if dst else 'CST')

def embed(g):
    lines=[]
    lines.append('💰 Normally **%s**'%g['worth'] if g.get('worth') else '💰 Free to keep')
    lines.append('⏰ Free until **%s**'%central(g['ends']) if g.get('ends') else '⏰ Free for a limited time')
    lines.append('%s %s'%(STORE_ICON.get(g['store'],'🎮'),g['store']))
    lines.append('👉 **[Claim it here](%s)**'%g['url'] if g.get('url') else '')
    e={'title':'🎮 FREE: %s'%g['title'][:200],'description':'\n'.join(l for l in lines if l),'color':COLOR}
    if g.get('url'): e['url']=g['url']
    if g.get('image'): e['thumbnail']={'url':g['image']}
    return e

def message(games, now):
    """One Discord message, up to 10 games (Discord's limit of embeds per message)."""
    es=[embed(g) for g in games[:10]]
    es[-1]['footer']={'text':'Free Game Alerts · claim before the time runs out · '+central(now)}
    return {'username':'Free Game Alerts','allowed_mentions':{'parse':[]},'embeds':es}


PING_ROLE_ID=os.environ.get('PING_ROLE_ID','').strip()   # 🔔 role members pick in onboarding; pinged on each post

def with_ping(payload):
    if PING_ROLE_ID.isdigit() and '<@&' not in (payload.get('content') or ''):
        payload=dict(payload,content=('<@&%s> '%PING_ROLE_ID)+(payload.get('content') or ''),allowed_mentions={'parse':[],'roles':[PING_ROLE_ID]})
    return payload

def deliver(hook, payload, opener=urllib.request.urlopen, sleep=time.sleep, attempts=3):
    payload=with_ping(payload)
    url=hook+('&' if '?' in hook else '?')+'wait=true'
    for a in range(attempts):
        try:
            req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','User-Agent':UA['User-Agent']},method='POST')
            with opener(req,timeout=30) as r: return 200<=r.status<300
        except urllib.error.HTTPError as e:
            if e.code==429:
                try: sleep(min(30,float(e.headers.get('Retry-After','2'))))
                except (TypeError,ValueError): sleep(2)
                continue
            if e.code<500: return False
        except (urllib.error.URLError,TimeoutError): pass
        if a<attempts-1: sleep(2**(a+1))
    return False

# --- run ------------------------------------------------------------------------------------------------------------
def run(hook, now=None, get=get_json, send=deliver, state_path=STATE_PATH, first_run_posts=True):
    now=now or dt.datetime.now(dt.timezone.utc); state=load_state(state_path)
    games,errors=collect(now,get)
    new=[g for g in games if state_key(g) not in state]
    new.sort(key=lambda g:(g['ends'] or now+dt.timedelta(days=365)))
    sent=0
    for i in range(0,len(new),10):
        batch=new[i:i+10]
        if send(hook,message(batch,now)):
            for g in batch: state[state_key(g)]=now.isoformat()
            sent+=len(batch)
    save_state(state,now,state_path)
    return {'found':len(games),'new':len(new),'posted':sent,'errors':errors}

def sample(now):
    """A clearly labelled SAMPLE message with made-up games, to check the layout. Records nothing."""
    games=[{'id':'s1','title':'Example Adventure','store':'Epic Games','worth':'$19.99','ends':now+dt.timedelta(days=6),'url':'https://store.epicgames.com/en-US/free-games','image':None},
           {'id':'s2','title':'Example Racer','store':'Steam','worth':'$9.99','ends':now+dt.timedelta(days=2),'url':'https://store.steampowered.com','image':None}]
    m=message(games,now)
    for e in m['embeds']: e['title']='🧪 SAMPLE — '+e['title']
    m['content']='🧪 **Sample message with made-up games** — this is what real alerts look like.'
    return m

def main():
    hook=os.environ.get('DISCORD_WEBHOOK_URL')
    if not hook: sys.exit('DISCORD_WEBHOOK_URL is not set (add it under Settings → Secrets and variables → Actions)')
    if os.environ.get('MODE')=='sample':
        ok=deliver(hook,sample(dt.datetime.now(dt.timezone.utc))); print('sample delivered' if ok else 'sample failed'); sys.exit(0 if ok else 1)
    rep=run(hook); print(json.dumps(rep))
    if rep['errors'] and not rep['found']: sys.exit('No feed could be read: '+'; '.join(rep['errors']))
if __name__=='__main__': main()
