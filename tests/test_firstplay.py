import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from urllib import error

ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('firstplay', ROOT/'scripts'/'firstplay.py')
fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)

class FakeClient:
    def __init__(self,pages):self.pages=iter(pages);self.calls=[]
    def get(self,path,params=None):self.calls.append((path,params));return next(self.pages)

def state(private=True):
    return {'currentUserId':'owner' if private else 'you','hasProfile':private,
            'games':[{'id':'game_one','title':'Puzzle game','status':'open','paymentStatus':'paid','slots':5,'reserved':1}],
            'sessions':[{'id':'s1','gameId':'game_one','creatorId':'owner','testerId':'tester','status':'submitted','dueAt':123,'feedback':{'answers':['private feedback body']}}] if private else [],
            'reviews':[{'id':'r1','sessionId':'s1','role':'creator','stars':3,'comment':'Peer rating, not game feedback'}]}

def poll(votes=(2,2)):
    return {'id':'poll_one','gameId':'game_one','question':'Which cover?','status':'open','options':[{'id':'a','text':'A','votes':votes[0]},{'id':'b','text':'B','votes':votes[1]}]}

class SkillTests(unittest.TestCase):
    def test_exact_money_and_limits(self):
        self.assertEqual(fp.quote('20',5)['total_cents'],11500)
        self.assertEqual(fp.quote('1.10',3)['fee_cents'],51)
        for amount in ['NaN','Infinity','0.99','1000.01','1.001',True]:
            with self.assertRaises(fp.FirstplayError):fp.quote(amount,1)
        for slots in [0,101,1.5,True]:
            with self.assertRaises(fp.FirstplayError):fp.quote('20',slots)

    def test_intake_missing_and_no_implicit_posting(self):
        draft=fp.prepare_game({'title':'Game'})
        self.assertIn('playUrl',draft['missing']);self.assertIn('reward',draft['missing'])
        self.assertFalse(draft['submitted']);self.assertFalse(draft['ready_for_site_draft'])
        valid={'title':'Game','description':'An indie puzzle game','genres':['Puzzle'],'platform':'Web browser','playUrl':'https://example.com/build','brief':'Test the first puzzle.','questions':['Where were you confused?'],'minutes':20,'reward':20,'slots':5}
        self.assertTrue(fp.prepare_game(valid)['ready_for_site_draft'])
        self.assertFalse(fp.prepare_game({**valid,'playUrl':'https://name:password@example.com'})['ready_for_site_draft'])
        self.assertFalse(fp.prepare_game({**valid,'title':'   '})['ready_for_site_draft'])

    def test_poll_media_and_eligibility_not_invented(self):
        valid={'gameId':'game_one','question':'Which cover?','format':'text','options':[{'text':'A'},{'text':'B'}]}
        self.assertTrue(fp.prepare_poll(valid)['ready_for_site_draft'])
        self.assertFalse(fp.prepare_poll(valid)['eligibility_verified'])
        self.assertFalse(fp.prepare_poll({**valid,'options':[{'text':'A'},{'text':'a'}]})['ready_for_site_draft'])
        self.assertFalse(fp.prepare_poll({**valid,'format':'image'})['ready_for_site_draft'])
        self.assertFalse(fp.prepare_poll({**valid,'media':{'type':'image','url':'https://example.com/x.png'}})['ready_for_site_draft'])

    def test_poll_pagination_scope_and_loop_detection(self):
        client=FakeClient([{'polls':[poll()],'nextCursor':'p2'},{'polls':[],'nextCursor':None}])
        self.assertEqual(len(fp.all_polls(client,'game_one')),1)
        self.assertEqual(client.calls[1][1]['before'],'p2')
        with self.assertRaises(fp.FirstplayError):fp.all_polls(FakeClient([{'polls':[],'nextCursor':'same'},{'polls':[],'nextCursor':'same'}]),'game_one')
        with self.assertRaises(fp.FirstplayError):fp.all_polls(FakeClient([{'polls':[poll()],'nextCursor':None}]),'other_game')
        with self.assertRaises(fp.FirstplayError):fp.all_polls(FakeClient([{'polls':[],'nextCursor':'more'}]),'game_one',max_pages=1)

    def test_private_game_feedback_peer_ratings_and_public_limits(self):
        private,snapshot=fp.build_report(state(),[poll()],'game_one',{},include_feedback=True)
        self.assertEqual(private['sessions'][0]['feedback']['answers'],['private feedback body'])
        self.assertEqual(private['peer_ratings'][0]['stars'],3)
        self.assertNotIn('private feedback body',json.dumps(snapshot))
        self.assertNotIn('Peer rating, not game feedback',json.dumps(snapshot))
        public,_=fp.build_report(state(False),[poll()],'game_one',{})
        self.assertIn('unavailable',public['coverage']['private_feedback'])
        self.assertEqual(public['peer_ratings'],[])
        # Even a bad state file cannot expose sessions the signed-in actor isn't participating in.
        raw=state();raw['sessions'][0]['creatorId']='someone_else'
        r,_=fp.build_report(raw,[],'game_one',{},include_feedback=True);self.assertEqual(r['sessions'],[])

    def test_baselines_vote_changes_ties_and_scope(self):
        report,old=fp.build_report(state(),[poll()],'game_one',{},now='before')
        self.assertTrue(fp.compare(None,old)['baseline'])
        self.assertEqual(report['polls'][0]['leaders'],['A','B'])
        _,new=fp.build_report(state(),[poll((1,5))],'game_one',{},now='after')
        change=fp.compare(old,new)['categories']['polls']['changed'][0]
        self.assertEqual(change['vote_delta'],2);self.assertEqual(change['option_deltas'],{'a':-1,'b':3})
        fresh=fp.compare({**old,'records':{**old['records'],'polls':{}}},new)
        self.assertEqual(fresh['categories']['polls']['newly_observed'],['poll_one'])
        self.assertFalse(fresh['categories']['polls']['changed'])
        _,public=fp.build_report(state(False),[],'game_one',{})
        with self.assertRaises(fp.FirstplayError):fp.compare(old,public)
        zero,_=fp.build_report(state(),[poll((0,0))],'game_one',{})
        self.assertIn('No leader: zero votes.',fp.markdown(zero))

    def test_redirect_and_access_errors_never_leak_or_downgrade(self):
        client=fp.Client('secret-test-token')
        for status in [302,401,403,429,503]:
            exc=error.HTTPError('https://theplaytest.io/api/state',status,'secret-test-token',{},None)
            with patch.object(client.opener,'open',side_effect=exc):
                with self.assertRaises(fp.FirstplayError) as cm:client.get('state')
                self.assertNotIn('secret-test-token',str(cm.exception))
                exc.close()
        with self.assertRaises(fp.FirstplayError):client.get('command')
        self.assertIsNone(fp.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example'))

    def test_atomic_local_baseline_permissions_and_failed_report_preserves_it(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'baseline.json';fp.atomic_json(path,{'sentinel':True})
            if os.name!='nt':self.assertEqual(path.stat().st_mode & 0o777,0o600)
            before=path.read_bytes()
            with patch.object(fp.Client,'get',side_effect=fp.FirstplayError('offline')),redirect_stderr(io.StringIO()):
                code=fp.main(['report','--game-id','game_one','--previous',str(path),'--snapshot',str(path)])
            self.assertEqual(code,1);self.assertEqual(path.read_bytes(),before)

    def test_cli_reports_without_private_dump_and_does_not_read_token_unless_requested(self):
        responses=[{'paidEnabled':False},state(False),{'polls':[poll()],'nextCursor':None}]
        out=io.StringIO()
        with patch.dict(os.environ,{'FIRSTPLAY_ID_TOKEN':'must-not-be-used'}),patch.object(fp.Client,'get',side_effect=responses),redirect_stdout(out):
            self.assertEqual(fp.main(['report','--game-id','game_one','--format','json']),0)
        report=json.loads(out.getvalue());self.assertEqual(report['scope']['visibility'],'public')
        self.assertNotIn('must-not-be-used',out.getvalue())
        self.assertNotIn('private feedback body',out.getvalue())
        with patch.dict(os.environ,{},clear=True),redirect_stderr(io.StringIO()):
            self.assertEqual(fp.main(['report','--game-id','game_one','--authenticated']),1)

    def test_packaging_links_and_entrypoint(self):
        skill=(ROOT/'SKILL.md').read_text()
        self.assertTrue(skill.startswith('---\nname: theplaytester\n'))
        import re
        for rel in re.findall(r'\]\(([^)#]+)',skill):
            if not rel.startswith('https:'):self.assertTrue((ROOT/rel).exists(),rel)
        self.assertNotIn('TODO',skill)
        self.assertTrue((ROOT/'LICENSE').exists())
        self.assertIn('$theplaytester',(ROOT/'agents'/'openai.yaml').read_text())

if __name__=='__main__':unittest.main()
