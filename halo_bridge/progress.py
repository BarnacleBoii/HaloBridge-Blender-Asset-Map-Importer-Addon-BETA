"""Progress based on real export counts and external-tool output, never estimated percentages."""
import time
import re
import threading
from pathlib import Path


class PreparationActivity:
    """Disk-backed event history; worker threads never access Blender data."""
    def __init__(self,path,report):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text('HaloBridge preparation activity\nTimes in [minutes:seconds] since preparation started. Stage numbers are not time estimates: stage 3 (Halo Tool compiling geometry) is usually the longest.\n',encoding='utf-8')
        self.report=report;self.started=time.monotonic();self.ended=None;self.phase='Validation';self.stage_number=0;self.current_log=''
        self.recent=();self.revision=0;self.last='';self.lock=threading.Lock()
    def event(self,message):
        message=str(message)
        with self.lock:
            if message==self.last:return
            self.last=message;elapsed=int(time.monotonic()-self.started)
            line=f'[{elapsed//60:02}:{elapsed%60:02}] {message}'
            with self.path.open('a',encoding='utf-8') as stream:stream.write(line+'\n')
            self.recent=(*self.recent[-5:],line);self.revision+=1
    def __call__(self,message):
        self.event(message);self.report(message)
    def heartbeat(self,message):self.report(message)
    def stage(self,number,name):
        self.stage_number=number
        self.phase=f'Stage {number}/5 — {name}'
        self(self.phase)

LIGHTING=[('faux_data_sync','Collecting lighting geometry'),('faux_farm_begin','Setting up test lighting')]
for key,label in [('dillum','Direct lighting'),('pcast','Photon tracing'),('radest','Radiosity'),('extillum','External illumination'),('fgather','Final gathering')]:
    LIGHTING.extend([('faux_farm_'+key,label),('faux_farm_'+key+'_merge','Merging '+label.lower())])
LIGHTING.extend([('faux_farm_finish','Finishing lightmaps'),('faux-build-linear-textures-with-intensity-from-quadratic','Converting lightmap textures'),('faux-compress-scenario-bitmaps-dxt5','Compressing lightmaps'),('faux-farm-compression-merge','Finalizing lighting')])


def tool_label(command):
    for index,(key,label) in enumerate(LIGHTING,1):
        if command==key:return f'Test lighting {index}/{len(LIGHTING)}: {label}'
    return {'structure':'Compiling level geometry and collision','bitmaps':'Compiling converted textures'}.get(command,command)


# Tool's structure import, in plain words. Tool processes many objects at once and
# names an object only in its warnings and errors, so steps describe the whole level.
STRUCTURE_STEPS=[
    ('parsing scene','Reading the exported level file'),
    ('looking for shaders','Matching materials to Halo 3 shaders'),
    ('building bsp3d','Building collision for the level\'s objects (Tool works on many at once and doesn\'t say which)'),
    ('moving planes','Optimizing collision planes'),('moving points','Optimizing collision planes'),
    ('merging planes','Optimizing collision planes'),('creating initial planes','Optimizing collision planes'),
    ('finding correct planes','Optimizing collision planes'),('splitting planes','Optimizing collision planes'),('copying planes','Optimizing collision planes'),
    ('building collision','Building the level\'s collision surfaces'),('breakable surfaces','Building the level\'s collision surfaces'),
    ('building triangle lists','Building render geometry'),('building render','Building render geometry'),('merging triangles','Building render geometry'),
    ('merging instances','Building render geometry'),('triangle-tangent','Building render geometry'),('triangle sections','Building render geometry'),
    ('building edge references','Building render geometry'),('reapplying geometry','Building render geometry'),
    ('detaching incorrect','Cleaning up triangles Tool can\'t use'),('welding','Welding vertices'),('copying vertices','Welding vertices'),('point','Welding vertices'),
    ('leaves','Dividing the level into visibility clusters'),('subclusters','Dividing the level into visibility clusters'),
    ('group neighbors','Dividing the level into visibility clusters'),('centroids','Dividing the level into visibility clusters'),
    ('slice groups','Dividing the level into visibility clusters'),('merge information','Dividing the level into visibility clusters'),
]
WARNING_TEXT=[(r'overlapping surfaces.*','overlapping surfaces (shows as red debug geometry in Sapien; usually harmless)'),
              (r'degenerate triangle.*','a zero-area triangle (Tool skips it)'),
              (r'Your texture coordinates are very large.*','very large texture coordinates (textures may look slightly blurry)')]
QUIET_WARNINGS=('is not renderable, but has flags',)  # HaloBridge's own collision-only copies


def describe(line,names=None,state=None):
    """A compiler line in plain words with Blender object names, or None to leave it out.

    Tool's percentages here belong to whichever of its parallel jobs printed last, so
    they jump around; they're left out. state remembers the level's mesh count."""
    names=names or {};state=state if state is not None else {}
    text=re.sub(r'\s+[|/\\-]\s*$','',line.strip())
    if not text or set(text)<={'.'}:return None
    poop=r'\(poop (hb_\d+)(?:\.\d+)?(?: merged)?\)'
    def objects(value):
        return re.sub(poop+r'\s*',lambda m:'on "'+names.get(m[1],m[1])+'": ',value)
    # Tool's crash report: one line, not its stack walk and assertion text.
    crash=('crash','ASSERTION FAILED','index>=','lifecycle','gamestate','stack walk','untracked version')
    if text.startswith('message ') or ('-FATAL-' in text and (not re.sub(poop,'',text.split('-FATAL-',1)[1]).strip() or any(c in text for c in crash))) \
            or ('WARNING' in text and any(c in text for c in crash)):
        found=re.search(poop,text)
        return 'Tool stopped (it crashed) while compiling '+('"'+names.get(found[1],found[1])+'"' if found else 'the level')+'; see the error above'
    if 'WARNING' in text or '-ERROR-' in text or '-FATAL-' in text:
        if any(q in text for q in QUIET_WARNINGS):return None
        kind='Error' if ('-ERROR-' in text or '-FATAL-' in text) else 'Warning'
        body=text.split('-ERROR-',1)[-1].split('-FATAL-',1)[-1].split('WARNING',1)[-1].strip()
        if 'failed to add import info' in body:return 'Note: Tool could not store a copy of this very large level file in the tag (harmless)'
        for pattern,value in WARNING_TEXT:body=re.sub(pattern,value,body)
        return kind+' '+objects(body)
    match=re.match(r'=== new instances: (\d+)',text)
    if match:return 'The level has '+f'{int(match[1]):,}'+' placed objects'
    match=re.match(r'=== new definiton: (\d+)',text)
    if match:
        state['meshes']=int(match[1])
        return 'They use '+f'{int(match[1]):,}'+' different meshes'
    if text.startswith('=== was') or text.startswith('=== starting import'):return None
    if text.startswith('=== imported structure'):return 'Geometry and collision compiled'
    lower=text.lower()
    for key,value in STRUCTURE_STEPS:
        if key in lower:
            if key=='building bsp3d' and state.get('meshes'):
                value='Building collision for the level\'s '+f'{state["meshes"]:,}'+' meshes (Tool works on many at once and doesn\'t say which)'
            return value
    return objects(re.sub(r'\s*\d+%\s*$','',text))


class ToolProgress:
    def __init__(self,command,log,report,names=None):
        self.names=names or {};self.structure=command=='structure'
        self.label=tool_label(command);self.log=Path(log);self.report=report
        self.started=time.monotonic();self.last_update=-float('inf');self.last_output=self.started
        self.size=0;self.latest=''
        self.process=None;self.sample=None;self.cpu=None;self.observed=None;self.activity='CPU activity: waiting for a sample.'
        self.last_event='';self.pending=b'';self.warned=set();self.state={}
        if hasattr(report,'current_log'):report.current_log=str(self.log)
        if hasattr(report,'event'):report.event('Compiler log: '+str(self.log))
    def bind_process(self,process,sample):
        self.process=process;self.sample=sample
    def __call__(self):
        now=time.monotonic()
        if now-self.last_update<1:return
        self.last_update=now
        try:
            size=self.log.stat().st_size
            if size!=self.size:
                with self.log.open('rb') as stream:
                    stream.seek(self.size if size>=self.size else 0);data=stream.read()
                data=self.pending+data.replace(b'\r',b'\n')
                parts=data.split(b'\n');self.pending=parts.pop()
                if self.process is not None and self.process.poll() is not None and self.pending:
                    parts.append(self.pending);self.pending=b''
                lines=[line.decode('utf-8',errors='replace').strip() for line in parts if line.strip()]
                for line in lines:
                    # Rotating spinner characters are activity, not new progress.
                    meaningful=describe(line,self.names,self.state) if self.structure else re.sub(r'\s+[|/\\-]\s*$','',line)
                    if not meaningful:continue
                    self.latest=meaningful[:200]
                    if meaningful.startswith('Warning '):
                        # One line per object and kind of warning, not one per surface.
                        if meaningful in self.warned:continue
                        self.warned.add(meaningful)
                    if meaningful!=self.last_event:
                        self.last_event=meaningful
                        if hasattr(self.report,'event'):self.report.event(self.label+': '+meaningful)
                self.size=size;self.last_output=now
        except OSError:pass  # Halo may temporarily hold its log exclusively.
        elapsed=int(now-self.started);quiet=int(now-self.last_output)
        if self.sample:
            sample=self.sample(self.process)
            if sample:
                cpu,memory=sample
                if self.cpu is not None:
                    busy=max(0,cpu-self.cpu)/max(.001,now-self.observed)*100
                    self.activity=f'CPU: {busy:.0f}% of one core | Memory: {memory/1048576:.0f} MB'
                    if busy<1:self.activity+=' | Little CPU activity; this alone does not prove a stall.'
                self.cpu=cpu;self.observed=now
        text=f'{self.label} | {elapsed//60:02}:{elapsed%60:02} elapsed\n{self.activity}'
        if self.latest:text+=f' | Last tool output ({quiet}s ago): {self.latest}'
        else:text+=' | Tool is running; waiting for progress output.'
        text+=('\nTime remaining: unknown. Tool compiles many objects at once and names one only when it has a problem with it.' if self.structure
               else '\nTime remaining: unknown. Any % above is this compiler substep only.')
        if quiet>=60:text+='\nNo new compiler output for '+str(quiet)+'s; activity does not guarantee successful completion.'
        getattr(self.report,'heartbeat',self.report)(text)
