import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from halo_bridge.progress import ToolProgress,tool_label,PreparationActivity

class ProgressTests(unittest.TestCase):
    def test_silent_tool_and_latest_output(self):
        with tempfile.TemporaryDirectory() as tmp,patch('halo_bridge.progress.time.monotonic') as clock:
            clock.return_value=100
            log=Path(tmp)/'tool.log';messages=[]
            progress=ToolProgress('faux_farm_dillum',log,messages.append)
            progress();self.assertIn('3/16',messages[-1]);self.assertIn('waiting for progress output',messages[-1])
            log.write_text('Starting\r25 percent\n',encoding='utf-8')
            clock.return_value=105;progress()
            self.assertIn('00:05 elapsed',messages[-1]);self.assertIn('25 percent',messages[-1])
            clock.return_value=115;progress();self.assertIn('10s ago',messages[-1])
            self.assertIn('16/16',tool_label('faux-farm-compression-merge'))

    def test_activity_retains_output_and_cpu_without_spinner_spam(self):
        with tempfile.TemporaryDirectory() as tmp,patch('halo_bridge.progress.time.monotonic') as clock:
            clock.return_value=0;messages=[]
            activity=PreparationActivity(Path(tmp)/'activity.log',messages.append)
            activity.stage(3,'Compile geometry and collision')
            log=Path(tmp)/'compiler.log';tool=ToolProgress('structure',log,activity)
            from types import SimpleNamespace
            process=SimpleNamespace(poll=lambda:None)
            samples=iter([(10,104857600),(12,104857600),(12,104857600)])
            tool.bind_process(process,lambda p:next(samples))
            log.write_text('Starting\ncreating initial planes...  0% \\\n',encoding='utf-8');tool()
            clock.return_value=2
            with log.open('a') as stream:stream.write('creating initial planes...  0% |\n')
            tool();self.assertIn('CPU: 100%',messages[-1]);self.assertIn('100 MB',messages[-1])
            clock.return_value=70;tool()
            self.assertIn('Little CPU activity',messages[-1]);self.assertIn('68s',messages[-1])
            self.assertIn('Time remaining: unknown',messages[-1])
            saved=activity.path.read_text(encoding='utf-8')
            # Tool's step names are translated into plain words, once per change.
            self.assertEqual(saved.count('Optimizing collision planes'),1)
            self.assertNotIn('creating initial planes',saved)
            self.assertIn('Starting',saved);self.assertIn('Stage 3/5',saved)
            self.assertEqual(activity.current_log,str(log))
            self.assertEqual(activity.stage_number,3)

    def test_short_process_final_output_without_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            from types import SimpleNamespace
            activity=PreparationActivity(Path(tmp)/'activity.log',lambda _:None)
            log=Path(tmp)/'tool.log';log.write_bytes(b'last line without newline')
            tool=ToolProgress('structure',log,activity)
            tool.bind_process(SimpleNamespace(poll=lambda:0),lambda p:None)
            tool()
            self.assertIn('last line without newline',activity.path.read_text())

    def test_structure_lines_in_plain_words(self):
        from halo_bridge.progress import describe
        names={'hb_190':'dry grass #3'};state={}
        self.assertEqual(describe('=== new definiton: 865looking for shaders',names,state),'They use 865 different meshes')
        self.assertIn('865 meshes',describe('building bsp3d children...... 68% /',names,state))
        self.assertNotIn('%',describe('building bsp3d children...... 68% /',names,state))
        self.assertEqual(describe("-ERROR- (poop hb_190.001) section 'global' has too many vertices (count=35764, max=32767)",names),
                         "Error on \"dry grass #3\": section 'global' has too many vertices (count=35764, max=32767)")
        self.assertIn('overlapping surfaces (shows as red',describe('WARNING (poop hb_190.001) overlapping surfaces',names))
        self.assertIsNone(describe("WARNING (poop hb_2.001) material '' is not renderable, but has flags that only make sense on render geometry",names))
        self.assertIsNone(describe('...',names))
        crash=[describe(line,names) for line in ('-FATAL- (poop hb_190.001) ','message (poop hb_190.001) crash: beginning stack walk',
               '-FATAL- (poop hb_190.001) tool  test x64 untracked version  Jan  3 2024','-FATAL- (poop hb_190.001) ### ASSERTION FAILED:  at array.cpp,#264',
               'WARNING (poop hb_190.001) lifecycle: CRASH')]
        self.assertEqual(set(crash),{'Tool stopped (it crashed) while compiling "dry grass #3"; see the error above'})
        self.assertIn('on "dry grass #3"',describe('WARNING (poop hb_190.001 merged) partially untextured geometry',names))

    def test_real_child_process_reporting(self):
        from halo_bridge.jobs import run_process
        with tempfile.TemporaryDirectory() as tmp:
            messages=[];activity=PreparationActivity(Path(tmp)/'activity.log',messages.append)
            log=Path(tmp)/'child.log'
            command='import time; print("starting",flush=True); end=time.monotonic()+1.3\nwhile time.monotonic()<end: pass\nprint("finished",flush=True)'
            result=run_process([sys.executable,'-c',command],log,status=ToolProgress('structure',log,activity))
            self.assertIn('finished',result)
            self.assertIn('finished',activity.path.read_text())
            self.assertTrue(any('CPU:' in m for m in messages))

if __name__=='__main__':unittest.main()
