import unittest, datetime as dt, json, tempfile
from pathlib import Path
import alerts as A

NOW=dt.datetime(2026,11,27,3,0,tzinfo=dt.timezone.utc)
def iso(d): return d.isoformat().replace('+00:00','Z')
EPIC={'data':{'Catalog':{'searchStore':{'elements':[
    {'id':'a1','title':'Hollow Knight','offerType':'BASE_GAME','price':{'totalPrice':{'fmtPrice':{'originalPrice':'$14.99'}}},
     'catalogNs':{'mappings':[{'pageSlug':'hollow-knight'}]},'keyImages':[{'type':'Thumbnail','url':'https://img/hk.png'}],
     'promotions':{'promotionalOffers':[{'promotionalOffers':[{'startDate':iso(NOW-dt.timedelta(days=1)),'endDate':iso(NOW+dt.timedelta(days=6)),'discountSetting':{'discountPercentage':0}}]}]}},
    {'id':'a2','title':'Next Week Game','promotions':{'promotionalOffers':[],'upcomingPromotionalOffers':[{'promotionalOffers':[{'startDate':iso(NOW+dt.timedelta(days=6)),'endDate':iso(NOW+dt.timedelta(days=13)),'discountSetting':{'discountPercentage':0}}]}]}},
    {'id':'a3','title':'Half Off Game','promotions':{'promotionalOffers':[{'promotionalOffers':[{'startDate':iso(NOW-dt.timedelta(days=1)),'endDate':iso(NOW+dt.timedelta(days=6)),'discountSetting':{'discountPercentage':50}}]}]}},
    {'id':'a4','title':'Some DLC','offerType':'DLC','promotions':{'promotionalOffers':[{'promotionalOffers':[{'startDate':iso(NOW-dt.timedelta(days=1)),'endDate':iso(NOW+dt.timedelta(days=6)),'discountSetting':{'discountPercentage':0}}]}]}},
]}}}}
GP=[{'id':11,'title':'Portal 2 (Steam) Giveaway','type':'Game','status':'Active','platforms':'PC, Steam','worth':'$9.99','end_date':'2026-11-30 23:59:00','open_giveaway_url':'https://gp/open/11','image':'https://gp/11.jpg'},
    {'id':12,'title':'Loot Pack','type':'DLC','status':'Active','platforms':'PC, Steam','worth':'N/A','end_date':'N/A'},
    {'id':13,'title':'Old Game (GOG) Giveaway','type':'Game','status':'Expired','platforms':'PC, GOG'},
    {'id':14,'title':'Hollow Knight (Epic Games) Giveaway','type':'Game','status':'Active','platforms':'PC, Epic Games Store','end_date':'N/A'}]
def get(url):
    if 'epicgames' in url: return EPIC
    return GP if 'platform=steam' in url else []

class Sources(unittest.TestCase):
    def test_epic_only_live_free_full_games(self):
        g=A.epic_games(EPIC,NOW); self.assertEqual([x['title'] for x in g],['Hollow Knight'])
        self.assertEqual(g[0]['url'],'https://store.epicgames.com/en-US/p/hollow-knight'); self.assertEqual(g[0]['worth'],'$14.99')
    def test_gamerpower_steam_games_only(self):
        g=A.gamerpower_games(GP,NOW); self.assertEqual([(x['title'],x['store']) for x in g],[('Portal 2','Steam')])
    def test_collect_survives_a_dead_feed(self):
        def bad(url):
            if 'epicgames' in url: raise OSError('down')
            return get(url)
        games,errors=A.collect(NOW,bad); self.assertEqual([x['title'] for x in games],['Portal 2']); self.assertEqual(errors,['Epic: OSError'])

class Run(unittest.TestCase):
    def setUp(self): self.d=tempfile.TemporaryDirectory(); self.state=Path(self.d.name,'s.json'); self.sent=[]
    def tearDown(self): self.d.cleanup()
    def send(self,hook,p): self.sent.append(p); return True
    def test_posts_once(self):
        r=A.run('H',NOW,get,self.send,self.state); self.assertEqual((r['found'],r['posted']),(2,2))
        titles=[e['title'] for e in self.sent[0]['embeds']]; self.assertEqual(titles,['🎮 FREE: Portal 2','🎮 FREE: Hollow Knight'])
        self.assertEqual(A.run('H',NOW+dt.timedelta(hours=3),get,self.send,self.state)['posted'],0); self.assertEqual(len(self.sent),1)
    def test_failed_delivery_retried_next_run(self):
        A.run('H',NOW,get,lambda h,p:False,self.state); self.assertEqual(A.run('H',NOW,get,self.send,self.state)['posted'],2)
    def test_message_reads_well(self):
        A.run('H',NOW,get,self.send,self.state); d=self.sent[0]['embeds'][1]['description']
        self.assertIn('💰 Normally **$14.99**',d); self.assertIn('⏰ Free until **Thu Dec 3, 3:00 AM CST**',d)
        self.assertIn('👉 **[Claim it here](https://store.epicgames.com/en-US/p/hollow-knight)**',d); self.assertEqual(self.sent[0]['allowed_mentions'],{'parse':[]})
    def test_central_time(self):
        self.assertEqual(A.central(dt.datetime(2026,12,3,16,0,tzinfo=dt.timezone.utc)),'Thu Dec 3, 10:00 AM CST')
        self.assertEqual(A.central(dt.datetime(2026,7,3,16,0,tzinfo=dt.timezone.utc)),'Fri Jul 3, 11:00 AM CDT')
    def test_sample_is_labelled(self):
        m=A.sample(NOW); self.assertTrue(all(e['title'].startswith('🧪 SAMPLE') for e in m['embeds']))

if __name__=='__main__': unittest.main()
