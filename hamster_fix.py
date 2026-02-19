#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAMSTER32 - ULEPSZONA WERSJA Z POPRAWKAMI
- Timeout dla dużych plików
- Obsługa unicode w nazwach
- Retry dla błędu 408
- Dokładniejsze liczenie bajtów
- Chunking dla dużych plików
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import socket,hashlib,re,sys,time,os,traceback,threading,getopt,getpass,ctypes,math,html
from itertools import groupby
from xml.dom.minidom import Document
import xml.parsers.expat

# ============================================================================
# POPRAWKI DLA DUŻYCH PLIKÓW I UNICODE
# ============================================================================

import unicodedata

def normalize_filename(filename):
    """Znormalizuj nazwę pliku - usuń problematyczne znaki unicode"""
    try:
        # Zamień znaki unicode na ASCII bez diakrytyków
        normalized = unicodedata.normalize('NFKD', filename)
        normalized = normalized.encode('ascii', 'ignore').decode('ascii')
        # Usuń dodatkowe spacje i znaki specjalne
        normalized = re.sub(r'[^\w\s.-]', '', normalized)
        normalized = re.sub(r'\s+', '.', normalized)
        return normalized.rstrip('.')
    except Exception as e:
        logger.warning(f"Błąd normalizacji {filename}: {e}")
        return filename

def safe_filename(path):
    """Bezpieczna nazwa pliku bez problematycznych znaków"""
    try:
        basename = os.path.basename(path)
        dirname = os.path.dirname(path)
        safe_name = normalize_filename(basename)
        if dirname:
            return os.path.join(dirname, safe_name)
        return safe_name
    except Exception as e:
        logger.warning(f"Błąd safe_filename: {e}")
        return path

# Zwiększyć timeout dla dużych transferów
TIMEOUT_LARGE_FILE = 600  # 10 minut dla dużych plików (>1GB)
TIMEOUT_MEDIUM_FILE = 300  # 5 minut dla średnich (100MB-1GB)
TIMEOUT_SMALL_FILE = 120   # 2 minuty dla małych (<100MB)

def get_timeout_for_file(filesize):
    """Ustaw timeout na podstawie rozmiaru pliku"""
    if filesize > 1024 * 1024 * 1024:  # > 1GB
        return TIMEOUT_LARGE_FILE
    elif filesize > 100 * 1024 * 1024:  # > 100MB
        return TIMEOUT_MEDIUM_FILE
    else:
        return TIMEOUT_SMALL_FILE

def get_file_checksum(filepath, chunk_size=65536):
    """Oblicz MD5 checksum pliku w chunksach"""
    try:
        md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                md5.update(data)
        return md5.hexdigest()
    except Exception as e:
        logger.warning(f"Błąd checksum dla {filepath}: {e}")
        return None

def verify_transfer_size(local_path, sent_bytes, expected_bytes):
    """Weryfikuj czy wysłano poprawną liczbę bajtów"""
    try:
        actual_size = os.path.getsize(local_path)

        # Tolerancja: do 64 bajty różnicy (mogą być headery)
        tolerance = 64

        if abs(actual_size - sent_bytes) <= tolerance:
            logger.info(f"✓ Transfer OK: {sent_bytes} bajtów")
            return True
        elif abs(expected_bytes - sent_bytes) <= tolerance:
            logger.info(f"✓ Transfer OK (expected): {sent_bytes} bajtów")
            return True
        else:
            logger.error(f"❌ Transfer ERROR: wysłano {sent_bytes}, plik {actual_size}, oczekiwano {expected_bytes}")
            return False
    except Exception as e:
        logger.error(f"Błąd verify_transfer_size: {e}")
        return False

def change_coding(t):
 try:
  if isinstance(t,str):return t
  elif isinstance(t,bytes):return t.decode('utf-8')
 except Exception as e:print(e)
 return str(t)
def to_unicode(t):
 try:
  if isinstance(t,bytes):t=t.decode('utf-8')
 except Exception as e:print(e)
 return t
def escape_name(t):return html.escape(str(t))
def unescape_name(t):
 t=str(t).replace("&quot;",'"').replace("&apos;","'").replace("&lt;","<").replace("&gt;",">").replace("&amp;","&")
 return t
_char=re.compile(r'&(\w+?);')
_dec=re.compile(r'&#(\d{2,4});')
_hex=re.compile(r'&#x(\d{2,4});')
def _char_unescape(m,defs=html.entities.entitydefs):
 try:return defs[m.group(1)]
 except KeyError:return m.group(0)
def unescape(s):
 result=_hex.sub(lambda x:chr(int(x.group(1),16)),_dec.sub(lambda x:chr(int(x.group(1))),_char.sub(_char_unescape,s)))
 return result
def debug_fun(tb):
 v=View()
 st=traceback.format_tb(tb)
 stack=[]
 while tb:
  stack.append(tb.tb_frame)
  tb=tb.tb_next
 v.print_("-"*10)
 v.print_(''.join(st))
 v.print_("Locals by frame, innermost last")
 for frame in stack:
  v.print_()
  v.print_("Frame %s in %s at line %s"%(frame.f_code.co_name,frame.f_code.co_filename,frame.f_lineno))
  for key,value in frame.f_locals.items():
   try:v.print_("\t%20s = "%key,value)
   except:v.print_("<ERROR WHILE PRINTING VALUE>")
 v.print_("-"*10)
class ParsingInterrupted(Exception):pass
class DictSAXHandler:
 def __init__(self,item_depth=0,xml_attribs=True,item_callback=lambda *args:True,attr_prefix='@',cdata_key='#text',force_cdata=False):
  self.path=[]
  self.stack=[]
  self.data=None
  self.item=None
  self.item_depth=item_depth
  self.xml_attribs=xml_attribs
  self.item_callback=item_callback
  self.attr_prefix=attr_prefix
  self.cdata_key=cdata_key
  self.force_cdata=force_cdata
 def startElement(self,name,attrs):
  self.path.append((name,attrs or None))
  if len(self.path)>self.item_depth:
   self.stack.append((self.item,self.data))
   attrs=dict((self.attr_prefix+key,value)for(key,value)in attrs.items())
   self.item=self.xml_attribs and attrs or None
   self.data=None
 def endElement(self,name):
  if len(self.path)==self.item_depth:
   item=self.item
   if item is None:item=self.data
   should_continue=self.item_callback(self.path,item)
   if not should_continue:raise ParsingInterrupted()
  if len(self.stack):
   item,data=self.item,self.data
   self.item,self.data=self.stack.pop()
   if self.force_cdata and item is None:item={}
   if item is not None:
    if data:item[self.cdata_key]=data
    self.push_data(name,item)
   else:self.push_data(name,data)
  else:self.item=self.data=None
  self.path.pop()
 def characters(self,data):
  if data.strip():
   if not self.data:self.data=data
   else:self.data+=data
 def push_data(self,key,data):
  if self.item is None:self.item={}
  try:
   value=self.item[key]
   if isinstance(value,list):value.append(data)
   else:self.item[key]=[value,data]
  except KeyError:self.item[key]=data
def parse(xml_input,*args,**kwargs):
 handler=DictSAXHandler(*args,**kwargs)
 parser=xml.parsers.expat.ParserCreate()
 parser.StartElementHandler=handler.startElement
 parser.EndElementHandler=handler.endElement
 parser.CharacterDataHandler=handler.characters
 if hasattr(xml_input,'read'):parser.ParseFile(xml_input)
 else:parser.Parse(xml_input,True)
 return handler.item
def dict2xml(xml_list):
 if isinstance(xml_list,list):return"".join([dict2xml(i)for i in xml_list])
 elif isinstance(xml_list,tuple):return"<"+xml_list[0]+">"+dict2xml(xml_list[1])+"</"+xml_list[0]+">"
 else:return str(xml_list)
class SOAP(object):
 def __init__(self):pass
 def soap_xml_to_dict(self,xml):return parse(xml)
 def soap_dict_to_xml(self,soap_dict,method):
  xml=dict2xml(soap_dict)
  text=xml.replace("<ROOT>","").replace("</ROOT>","")
  prefix='<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><'+method+' xmlns="http://chomikuj.pl/">'
  suffix="</"+method+"></s:Body></s:Envelope>"
  return prefix+text+suffix
if sys.platform.startswith('win'):
 SHORT=ctypes.c_short
 WORD=ctypes.c_ushort
 STD_OUTPUT_HANDLE=-11
 class COORD(ctypes.Structure):
  _fields_=[('X',SHORT),('Y',SHORT)]
 class SMALL_RECT(ctypes.Structure):
  _fields_=[("Left",ctypes.c_short),("Top",ctypes.c_short),("Right",ctypes.c_short),("Bottom",ctypes.c_short)]
 class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
  _fields_=[("Size",COORD),("CursorPosition",COORD),("Attributes",ctypes.c_short),("Window",SMALL_RECT),("MaximumWindowSize",COORD)]
 class CONSOLE_CURSOR_INFO(ctypes.Structure):
  _fields_=[('dwSize',ctypes.c_ulong),('bVisible',ctypes.c_int)]
 hconsole=ctypes.windll.kernel32.GetStdHandle(-11)
 sbinfo=CONSOLE_SCREEN_BUFFER_INFO()
 csinfo=CONSOLE_CURSOR_INFO()
 to_int=lambda number,default:number and int(number)or default
 class ConsoleWin(object):
  def __init__(self):
   self.hconsole=ctypes.windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
   self.orig_sbinfo=CONSOLE_SCREEN_BUFFER_INFO()
   self.orig_csinfo=CONSOLE_CURSOR_INFO()
   ctypes.windll.kernel32.GetConsoleScreenBufferInfo(self.hconsole,ctypes.byref(self.orig_sbinfo))
   ctypes.windll.kernel32.GetConsoleCursorInfo(hconsole,ctypes.byref(self.orig_csinfo))
  def screen_buffer_info(self):
   sbinfo=CONSOLE_SCREEN_BUFFER_INFO()
   ctypes.windll.kernel32.GetConsoleScreenBufferInfo(self.hconsole,ctypes.byref(sbinfo))
   return sbinfo
  def clear_line(self,param=2):
   mode=param and int(param)or 0
   sbinfo=self.screen_buffer_info()
   if mode==1:
    line_start=COORD(0,sbinfo.CursorPosition.Y)
    line_length=sbinfo.Size.X
   elif mode==2:
    line_start=COORD(sbinfo.CursorPosition.X,sbinfo.CursorPosition.Y)
    line_length=sbinfo.Size.X-sbinfo.CursorPosition.X
   else:
    line_start=sbinfo.CursorPosition
    line_length=sbinfo.Size.X-sbinfo.CursorPosition.X
   chars_written=ctypes.c_int()
   ctypes.windll.kernel32.FillConsoleOutputCharacterA(self.hconsole,ctypes.c_char(b' '),line_length,line_start,ctypes.byref(chars_written))
   ctypes.windll.kernel32.FillConsoleOutputAttribute(self.hconsole,sbinfo.Attributes,line_length,line_start,ctypes.byref(chars_written))
  def move_cursor(self,x_offset=0,y_offset=0):
   sbinfo=self.screen_buffer_info()
   new_pos=COORD(min(max(0,sbinfo.CursorPosition.X+x_offset),sbinfo.Size.X),min(max(0,sbinfo.CursorPosition.Y+y_offset),sbinfo.Size.Y))
   ctypes.windll.kernel32.SetConsoleCursorPosition(self.hconsole,new_pos)
  def move_up(self,param):
   self.move_cursor(y_offset=-to_int(param,1))
  def move_down(self,param):
   self.move_cursor(y_offset=to_int(param,1))
  def prev_line(self):
   sbinfo=self.screen_buffer_info()
   new_pos=COORD(min(0,sbinfo.Size.X),min(max(0,sbinfo.CursorPosition.Y-1),sbinfo.Size.Y))
   ctypes.windll.kernel32.SetConsoleCursorPosition(self.hconsole,new_pos)
  def next_line(self):
   sbinfo=self.screen_buffer_info()
   new_pos=COORD(min(0,sbinfo.Size.X),min(max(0,sbinfo.CursorPosition.Y+1),sbinfo.Size.Y))
   ctypes.windll.kernel32.SetConsoleCursorPosition(self.hconsole,new_pos)
else:
 class ConsoleUnix(object):
  def __init__(self):
   self.ESC=chr(27)
  def clear_line(self,param=2):
   mode=param and int(param)or 0
   if mode==1:sys.stdout.write(self.ESC+'[1K')
   elif mode==2:sys.stdout.write(self.ESC+'[2K')
   else:sys.stdout.write(self.ESC+'[0K')
  def move_cursor(self,x_offset=0,y_offset=0):
   if x_offset>=0:sys.stdout.write(self.ESC+'[%dC'%(x_offset))
   else:sys.stdout.write(self.ESC+'[%dD'%(-x_offset))
   if y_offset>=0:sys.stdout.write(self.ESC+'[%dB'%(y_offset))
   else:sys.stdout.write(self.ESC+'[%dA'%(-y_offset))
  def move_up(self,param):
   sys.stdout.write(self.ESC+'[%dA'%(param))
  def move_down(self,param):
   sys.stdout.write(self.ESC+'[%dB'%(param))
  def prev_line(self):
   sys.stdout.write(self.ESC+'[1A')
   sys.stdout.write('\r')
  def next_line(self):
   sys.stdout.write(self.ESC+'[1B')
   sys.stdout.write('\r')
def change_unit_bytes(value):
 if value<1024:return(value,'B')
 elif value<1048576:return(value/1024.,'kB')
 elif value<1024**3:return(value/1048576.,'MB')
 else:return(value/(1024.**3),'GB')
def change_unit_time(value):
 if value<60:return(value,'s.')
 elif value<60*60:return(value/60.,'min')
 else:return(value/3600.,'h.')
class ProgressBar(object):
 def __init__(self,total=100,rate_refresh=0.5,count=0,name=""):
  self.name=name
  self.total=total
  if self.total==0:self.total=1
  self.rate_refresh=rate_refresh
  self.meter_ticks=20
  self.meter_division=float(self.total)/self.meter_ticks
  self.count=count
  self.count_total=count
  self.rate_current=0.0
  self.rate_current_total=0.0
  self.meter_value=int(self.count/self.meter_division)
  self.meter_value_total=int(self.count/self.meter_division)
  self.last_update=None
  self.rate_count=0
  self.last_refresh=0
  self.history_len=10
  self.history=[None]*self.history_len
  self.history_index=0
  self.lock=threading.Lock()
 def update(self,count):
  now=time.time()
  rate=0.0
  self.count+=count
  self.count=min(self.count,self.total)
  if self.last_update==None:self.last_update=now
  value=int(self.count/self.meter_division)
  if value>self.meter_value:self.meter_value=value
  self.rate_count+=count
  if now-self.last_update>0.5:
   self.history[self.history_index]=self.rate_count/float(now-self.last_update)
   self.history_index=(self.history_index+1)%self.history_len
   hist=[i for i in self.history if i!=None]
   self.rate_current=sum(hist)/float(len(hist))
   self.rate_count=0
   self.last_update=now
   self.update_to_display()
 def update_to_display(self):
  self.meter_value_total=self.meter_value
  self.count_total=self.count
  self.rate_current_total=self.rate_current
 def get_meter(self,**kw):
  bar='-'*self.meter_value_total
  pad=' '*(self.meter_ticks-self.meter_value_total)
  perc=(float(self.count_total)/self.total)*100
  rate_current,unit=change_unit_bytes(self.rate_current_total)
  downloaded,unit_d=change_unit_bytes(self.count_total)
  total,unit_t=change_unit_bytes(self.total)
  if self.rate_current_total==0:
   rest_time=float("inf")
   unit_time=''
  else:
   rest_time,unit_time=change_unit_time((self.total-self.count_total)/float(self.rate_current_total))
  return'[%s>%s] %d%%  %.1f%s/sec  %.1f%s/%.1f%s  %.1f%s'%(bar,pad,perc,rate_current,unit,downloaded,unit_d,total,unit_t,rest_time,unit_time)
def create_console():
 if sys.platform.startswith('win'):return ConsoleWin()
 else:return ConsoleUnix()
def change_print_coding(text):
 return str(text)
class View(object):
 def __init__(self):
  self.lock=threading.Lock()
  self.progress_bars=[]
  self.console=create_console()
  self.last_update=time.time()
 def print_(self,*args):
  self.lock.acquire()
  try:
   self.last_update=time.time()
   self._wipe_progress_bars()
   for i in args:print(change_print_coding(i),end=' ')
   print()
   self._show_progress_bars()
   sys.stdout.flush()
  finally:self.lock.release()
 def _wipe_progress_bars(self):
  for progress_bar in self.progress_bars:
   self.console.prev_line()
   self.console.clear_line(2)
   self.console.prev_line()
   self.console.clear_line(2)
  sys.stdout.flush()
 def _show_progress_bars(self):
  for progress_bar in self.progress_bars:
   print(change_print_coding(progress_bar.name[-80:]),end=' ')
   sys.stdout.write('\r\n')
   sys.stdout.write(progress_bar.get_meter())
   sys.stdout.write('\r\n')
  sys.stdout.flush()
 def update_progress_bars(self):
  self.lock.acquire()
  try:
   now=time.time()
   if now-self.last_update>0.5:
    self._wipe_progress_bars()
    self._show_progress_bars()
    sys.stdout.flush()
    self.last_update=time.time()
  finally:self.lock.release()
 def add_progress_bar(self,progress_bar_object):
  self.lock.acquire()
  try:
   print(change_print_coding(progress_bar_object.name),end=' ')
   sys.stdout.write('\r\n')
   sys.stdout.write(progress_bar_object.get_meter())
   sys.stdout.write('\r\n')
   self.progress_bars.append(progress_bar_object)
  finally:self.lock.release()
 def delete_progress_bar(self,progress_bar_object):
  self.lock.acquire()
  try:
   self._wipe_progress_bars()
   print(change_print_coding(progress_bar_object.name),end=' ')
   sys.stdout.write('\r\n')
   progress_bar_object.update_to_display()
   sys.stdout.write(progress_bar_object.get_meter())
   sys.stdout.write('\r\n')
   self.progress_bars.remove(progress_bar_object)
   self._show_progress_bars()
  finally:self.lock.release()
class Model(object):
 def __init__(self):
  self.view=View()
  self.lock=threading.Lock()
  self.chdirs_lock=threading.Lock()
  self.notuploaded_file_name='notuploaded.txt'
  self.uploaded_file_name='uploaded.txt'
  self.uploaded=[]
  self.notuploaded=[]
  if not os.path.exists(self.uploaded_file_name):open(self.uploaded_file_name,'w').close()
  f=open(self.uploaded_file_name,'r',encoding='utf-8',errors='ignore')
  self.uploaded=f.read().split('\n')
  self.uploaded=set([i.strip()for i in self.uploaded])
  f.close()
  if not os.path.exists(self.notuploaded_file_name):open(self.notuploaded_file_name,"w").close()
  f=open(self.notuploaded_file_name,"r",encoding='utf-8',errors='ignore')
  files=[i.strip()for i in f.readlines()]
  f.close()
  self.notuploaded_resume=[]
  self.notuploaded_normal=[]
  self.pending=[]
  for f in files:
   try:
    filepath,filename,folder_id,chomik_id,token,host,port,stamp=re.findall(r"([^\t]*)\t([^\t]*)\t([^\t]*)\t([^\t]*)\t([^\t]*)\t([^\t]*)\t([^\t]*)\t([^\t]*)",f)[0]
    self.notuploaded_resume.append((filepath,filename,folder_id,chomik_id,token,host,port,stamp))
   except IndexError as e:self.notuploaded_normal.append(f.strip())
 def _aux_remove_notuploaded_resume(self,filepath):
  filepath=str(filepath)
  it=0
  while it<len(self.notuploaded_resume):
   i=self.notuploaded_resume[it]
   if i[0]==filepath:self.notuploaded_resume.remove(i)
   it+=1
 def _aux_remove_notuploaded_normal(self,filepath):
  filepath=str(filepath)
  it=0
  while it<len(self.notuploaded_normal):
   i=self.notuploaded_normal[it]
   if i==filepath:self.notuploaded_normal.remove(i)
   it+=1
 def _aux_remove_pending(self,filepath):
  filepath=str(filepath)
  it=0
  while it<len(self.pending):
   i=self.pending[it]
   if i==filepath:self.pending.remove(i)
   it+=1
 def add_notuploaded_normal(self,filepath):
  self.lock.acquire()
  filepath=str(filepath)
  try:
   if not filepath in self.notuploaded_normal:
    self.notuploaded_normal.append(filepath)
    f=open(self.notuploaded_file_name,'a',encoding='utf-8')
    f.write(filepath)
    f.write('\r\n')
    f.close()
  finally:self.lock.release()
 def add_notuploaded_resume(self,filepath,filename,folder_id,chomik_id,token,host,port,stamp):
  self.lock.acquire()
  filepath=str(filepath)
  try:
   self._aux_remove_notuploaded_resume(filepath)
   self._aux_remove_notuploaded_normal(filepath)
   self._save_notuploaded()
   self.notuploaded_resume.append((filepath,filename,folder_id,chomik_id,token,host,port,stamp))
   f=open(self.notuploaded_file_name,'a',encoding='utf-8')
   f.write(str(filepath)+'\t')
   f.write(str(filename)+'\t')
   f.write(str(folder_id)+'\t')
   f.write(str(chomik_id)+'\t')
   f.write(str(token)+'\t')
   f.write(str(host)+'\t')
   f.write(str(port)+'\t')
   f.write(str(stamp))
   f.write('\r\n')
   f.close()
  finally:self.lock.release()
 def remove_notuploaded(self,filepath):
  self.lock.acquire()
  filepath=str(filepath)
  try:
   self._aux_remove_notuploaded_resume(filepath)
   self._aux_remove_notuploaded_normal(filepath)
   self._save_notuploaded()
  finally:self.lock.release()
 def _save_notuploaded(self):
  f=open(self.notuploaded_file_name,'w',encoding='utf-8')
  for nu in self.notuploaded_resume:
   l=[str(i)for i in list(nu)]
   f.write('\t'.join(l))
   f.write('\r\n')
  for nu in self.notuploaded_normal:
   f.write(str(nu))
   f.write('\r\n')
  f.close()
 def get_notuploaded_resume(self):
  return self.notuploaded_resume
 def add_uploaded(self,filepath):
  self.lock.acquire()
  filepath=str(filepath)
  try:
   self.uploaded.add(filepath)
   f=open(self.uploaded_file_name,'a',encoding='utf-8')
   f.write(filepath+'\r\n')
   f.close()
  finally:self.lock.release()
 def in_uploaded(self,filepath):
  self.lock.acquire()
  filepath=str(filepath)
  try:result=filepath in self.uploaded
  finally:self.lock.release()
  return result
 def add_to_pending(self,filepath):pass
 def remove_from_pending(self,filepath):
  self.lock.acquire()
  try:self._aux_remove_pending(filepath)
  finally:self.lock.release()
 def is_uploaded_or_pended_and_add(self,filepath):
  self.lock.acquire()
  try:
   result1=filepath in self.uploaded
   result2=filepath in self.pending
   result=(result1 or result2)
   if(not result1)and(not result2):self.pending.append(filepath)
  finally:self.lock.release()
  return result
 def return_chdirlock(self):
  return self.chdirs_lock
glob_timeout=35
login_ip="box.chomikuj.pl"
login_port=80
version="2.0.8.2"
client="ChomikBox-"+version
class ChomikException(Exception):
 def __init__(self,filepath,filename,folder_id,chomik_id,token,server,port,stamp,excpt=None):
  Exception.__init__(self)
  self.filepath=filepath
  self.filename=filename
  self.folder_id=folder_id
  self.chomik_id=chomik_id
  self.token=token
  self.server=server
  self.port=port
  self.stamp=stamp
  self.excpt=excpt
 def __str__(self):
  return str(self.excpt)
 def get_excpt(self):
  return self.excpt
 def args(self):
  return(self.filepath,self.filename,self.folder_id,self.chomik_id,self.token,self.server,self.port,self.stamp)
class Chomik(object):
 def __init__(self,view_=None,model_=None,debug=False):
  if view_==None:self.view=View()
  else:self.view=view_
  if model_==None:self.model=Model()
  else:self.model=model_
  self.soap=SOAP()
  self.folders_dom={}
  self.ses_id=''
  self.chomik_id='0'
  self.folder_id='0'
  self.cur_fold=[]
  self.user=''
  self.password=''
  self.last_login=0
  self.debug=debug
  self.cookie=''
 def send(self,content):
  counter=0
  while counter<100:
   try:
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.settimeout(glob_timeout)
    sock.connect((login_ip,login_port))
    sock.send(content.encode('utf-8'))
    resp=b""
    kRespSize=2056
    while True:
     tmp=sock.recv(kRespSize)
     resp+=tmp
     if tmp.endswith(b"\r\n\r\n")and resp.count(b"\r\n\r\n")>=2 or tmp==b'':break
    sock.close()
    resp=resp.decode('utf-8',errors='ignore')
    if "Set-Cookie: __cfduid=" in resp:
     self.cookie=re.findall("Set-Cookie: __cfduid=([^;]*)",resp)[0]
    resp=resp.partition("\r\n\r\n")[2]
    resp=re.sub(r"\r\n\w{1,10}\r\n","",resp)
    _,_,resp=resp.partition("<")
    resp="<"+resp
    resp,_,_=resp.rpartition(">")
    resp=resp+">"
    return resp
   except socket.error as error:
    self.view.print_("Nieudane polaczenie: "+str(error))
    self.view.print_("Proba "+str(counter)+" z 100")
    counter+=1
 def login(self,user,password):
  self.user=user
  self.password=password
  if self.relogin()==True:
   self.get_dir_list()
   return True
  else:return False
 def relogin(self):
  if self.last_login+300>time.time():return True
  self.last_login=time.time()
  password=hashlib.md5(self.password.encode('utf-8')).hexdigest()
  xml_dict=[('ROOT',[('name',self.user),('passHash',password),('ver','4'),('client',[('name','chomikbox'),('version',version)])])]
  xml_content=self.soap.soap_dict_to_xml(xml_dict,"Auth").strip()
  xml_len=len(xml_content)
  header="""POST /services/ChomikBoxService.svc HTTP/1.1\r\n"""
  header+="""SOAPAction: http://chomikuj.pl/IChomikBoxService/Auth\r\n"""
  header+="""Content-Type: text/xml;charset=utf-8\r\n"""
  header+="""Content-Length: %d\r\n"""%xml_len
  header+="""Connection: Keep-Alive\r\n"""
  header+="""Accept-Encoding: identity\r\n"""
  header+="""Accept-Language: pl-PL,en,*\r\n"""
  header+="""User-Agent: Mozilla/5.0\r\n"""
  header+="""Host: box.chomikuj.pl\r\n\r\n"""
  header+=xml_content
  resp=self.send(header)
  resp_dict=self.soap.soap_xml_to_dict(resp)
  status=resp_dict['s:Envelope']['s:Body']['AuthResponse']['AuthResult']['a:status']
  if status!='Ok':
   self.view.print_("Blad(relogin):")
   self.view.print_(status)
   return False
  try:
   chomik_id=resp_dict['s:Envelope']['s:Body']['AuthResponse']['AuthResult']['a:hamsterId']
   ses_id=resp_dict['s:Envelope']['s:Body']['AuthResponse']['AuthResult']['a:token']
   self.ses_id=ses_id
   self.chomik_id=chomik_id
   if self.ses_id=="-1"or self.chomik_id=="-1":return False
  except IndexError as e:
   self.view.print_("Blad(relogin):")
   self.view.print_(e)
   return False
  else:return True
 def get_dir_list(self,folder_id=0,folder_dom_root={}):
  self.relogin()
  xml_dict=[('ROOT',[('token',self.ses_id),('hamsterId',self.chomik_id),('folderId',folder_id),('depth',0)])]
  xml_content=self.soap.soap_dict_to_xml(xml_dict,"Folders").strip()
  xml_len=len(xml_content)
  header="""POST /services/ChomikBoxService.svc HTTP/1.1\r\n"""
  header+="""SOAPAction: http://chomikuj.pl/IChomikBoxService/Folders\r\n"""
  header+="""Content-Type: text/xml;charset=utf-8\r\n"""
  if self.cookie!='':header+="""Cookie: __cfduid={0}\r\n""".format(self.cookie)
  header+="""Content-Length: %d\r\n"""%xml_len
  header+="""Connection: Keep-Alive\r\n"""
  header+="""Accept-Encoding: identity\r\n"""
  header+="""Accept-Language: pl-PL,en,*\r\n"""
  header+="""User-Agent: Mozilla/5.0\r\n"""
  header+="""Host: box.chomikuj.pl\r\n\r\n"""
  header+=xml_content
  resp=self.send(header)
  resp_dict=self.soap.soap_xml_to_dict(resp)
  status=resp_dict['s:Envelope']['s:Body']['FoldersResponse']['FoldersResult']['a:status']
  if status!='Ok':
   self.view.print_("Blad(pobieranie listy folderow):")
   self.view.print_(status)
   return False
  if folder_id==0:self.folders_dom=resp_dict['s:Envelope']['s:Body']['FoldersResponse']['FoldersResult']['a:folder']
  else:
   folder_dom_root['folders']=resp_dict['s:Envelope']['s:Body']['FoldersResponse']['FoldersResult']['a:folder']['folders']
   return True
  return True
 def cur_adr(self,atr=None):
  if atr==None:return self.cur_fold,self.folder_id
  else:self.cur_fold,self.folder_id=atr
 def chdirs(self,directories):
  folders=self.cur_fold+[i.replace("/","")for i in directories.split('/')if i!='']
  fold=[]
  for f in folders:
   if f=="..":
    if f!=[]:del(fold[-1])
   else:fold.append(f)
  folders=fold
  fold=[]
  folder_id='0'
  result,dom,folder_id=self.__access_node(folders)
  if result==True:
   self.cur_fold=folders
   self.folder_id=folder_id
  else:
   result,dom,folder_id=self.__create_nodes(folders)
   if result==False:return False
  self.cur_fold=folders
  self.folder_id=folder_id
  return True
 def __access_node(self,folders_list):
  dom=self.folders_dom
  fold=[]
  folder_id='0'
  for f in folders_list:
   list_of_subfolders=dom.get('folders',{}).get('FolderInfo',{})
   if isinstance(list_of_subfolders,dict):list_of_subfolders=[list_of_subfolders]
   name=self.__dirname_refinement(f)
   name=str(name)
   if name in[unescape_name(i.get("name",""))for i in list_of_subfolders]:
    for i in list_of_subfolders:
     if name==unescape_name(i.get("name","")):
      dom=i
      folder_id=i["id"]
      break
   else:return(False,None,None)
  return(True,dom,folder_id)
 def __create_nodes(self,folder_list):
  folder_id='0'
  fold=[]
  dom=self.folders_dom
  for f in folder_list:
   list_of_subfolders=dom.get('folders',{}).get('FolderInfo',{})
   if isinstance(list_of_subfolders,dict):list_of_subfolders=[list_of_subfolders]
   name=self.__dirname_refinement(f)
   name=str(name)
   if name in[unescape_name(i.get("name",""))for i in list_of_subfolders]:
    for i in list_of_subfolders:
     if name==unescape_name(i.get("name","")):
      dom=i
      folder_id=i["id"]
      fold.append(f)
      break
   else:
    self.mkdir(name,folder_id)
    self.get_dir_list(folder_id,dom)
    result,dom,folder_id=self.__access_node(fold+[f])
    if result==False:return(False,None,None)
    else:fold.append(f)
  return(True,dom,folder_id)
 def __dirname_refinement(self,dirname):
  dirname=str(dirname)[:256]
  not_allowed=["\\","/",":","*","?",'"',"<",">","|"]
  for ch in not_allowed:
   if ch in dirname:dirname=dirname.replace(ch,"")
  if dirname.startswith("."):dirname=dirname[1:]
  if dirname.endswith("."):dirname=dirname[:-1]
  return dirname
 def mkdir(self,dirname,folder_id=None):
  dirname=self.__dirname_refinement(dirname)
  self.relogin()
  if folder_id==None:folder_id=self.folder_id
  dirname=str(dirname)
  self.view.print_("Creating",dirname,"directory")
  dirname=escape_name(dirname)
  xml_dict=[('ROOT',[('token',self.ses_id),('newFolderId',folder_id),('name',dirname)])]
  xml_content=self.soap.soap_dict_to_xml(xml_dict,"AddFolder").strip()
  xml_len=len(xml_content)
  header="""POST /services/ChomikBoxService.svc HTTP/1.1\r\n"""
  header+="""SOAPAction: http://chomikuj.pl/IChomikBoxService/AddFolder\r\n"""
  header+="""Content-Type: text/xml;charset=utf-8\r\n"""
  if self.cookie!='':header+="""Cookie: __cfduid={0}\r\n""".format(self.cookie)
  header+="""Content-Length: %d\r\n"""%xml_len
  header+="""Connection: Keep-Alive\r\n"""
  header+="""Accept-Language: pl-PL,en,*\r\n"""
  header+="""User-Agent: Mozilla/5.0\r\n"""
  header+="""Host: box.chomikuj.pl\r\n\r\n"""
  header+=xml_content
  resp=self.send(header)
  resp_dict=self.soap.soap_xml_to_dict(resp)
  status=resp_dict['s:Envelope']['s:Body']['AddFolderResponse']['AddFolderResult']['status']['#text']
  if status=='Ok':
   self.view.print_("Creation success\r\n")
   return True
  else:
   error_msg=resp_dict['s:Envelope']['s:Body']['AddFolderResponse']['AddFolderResult']['errorMessage']['#text']
   if error_msg=='NameExistsAtDestination':return True
   else:
    self.view.print_("Creation fail")
    self.view.print_(error_msg)
    return False
 def rmdir(self):
  self.relogin()
  self.view.print_("Removing current directory")
  xml_dict=[('ROOT',[('token',self.ses_id),('folderId',self.folder_id),('force','1')])]
  xml_content=self.soap.soap_dict_to_xml(xml_dict,"RemoveFolder").strip()
  xml_len=len(xml_content)
  header="""POST /services/ChomikBoxService.svc HTTP/1.1\r\n"""
  header+="""SOAPAction: http://chomikuj.pl/IChomikBoxService/RemoveFolder\r\n"""
  header+="""Content-Type: text/xml;charset=utf-8\r\n"""
  if self.cookie!='':header+="""Cookie: __cfduid={0}\r\n""".format(self.cookie)
  header+="""Content-Length: %d\r\n"""%xml_len
  header+="""Connection: Keep-Alive\r\n"""
  header+="""Accept-Language: pl-PL,en,*\r\n"""
  header+="""User-Agent: Mozilla/5.0\r\n"""
  header+="""Host: box.chomikuj.pl\r\n\r\n"""
  header+=xml_content
  resp=self.send(header)
  resp_dict=self.soap.soap_xml_to_dict(resp)
  status=resp_dict['s:Envelope']['s:Body']['RemoveFolderResponse']['RemoveFolderResult']['a:status']
  if status=='Ok':
   self.view.print_("Removal success\r\n")
   return True
  else:
   self.view.print_("Removal fail")
   self.view.print_(status)
   return False
 def upload(self,filepath,filename):
  self.relogin()
  filename_tmp=str(filename)
  filename_tmp=escape_name(filename_tmp)
  self.model.add_notuploaded_normal(filepath)
  token,stamp,server,port=self.__upload_get_tokens(filepath,filename)
  if token is None:
   self.view.print_("Nie udalo sie uzyskac tokenow do uploadu")
   return False
  self.model.add_notuploaded_resume(filepath,filename,self.folder_id,self.chomik_id,token,server,port,stamp)
  result=self.__upload_with_resume_option(filepath,filename,token,stamp,server,port,self.chomik_id,self.folder_id)
  if result==True:self.model.remove_notuploaded(filepath)
  return result
 def __upload_with_resume_option(self,filepath,filename,token,stamp,server,port,chomik_id,folder_id):
  try:result=self.__upload(filepath,filename,token,stamp,server,port)
  except(socket.error,socket.timeout) as e:
   self.view.print_("Wznawianie\n")
   result=self.resume(filepath,filename,folder_id,chomik_id,token,server,port,stamp)
  return result
 def __upload_get_tokens(self,filepath,filename):
  xml_dict=[('ROOT',[('token',self.ses_id),('folderId',self.folder_id),('fileName',str(filename))])]
  xml_content=self.soap.soap_dict_to_xml(xml_dict,"UploadToken").strip()
  xml_len=len(xml_content)
  header="""POST /services/ChomikBoxService.svc HTTP/1.1\r\n"""
  header+="""SOAPAction: http://chomikuj.pl/IChomikBoxService/UploadToken\r\n"""
  header+="""Content-Type: text/xml;charset=utf-8\r\n"""
  if self.cookie!='':header+="""Cookie: __cfduid={0}\r\n""".format(self.cookie)
  header+="""Content-Length: %d\r\n"""%xml_len
  header+="""Connection: Keep-Alive\r\n"""
  header+="""Accept-Language: pl-PL,en,*\r\n"""
  header+="""User-Agent: Mozilla/5.0\r\n"""
  header+="""Host: box.chomikuj.pl\r\n\r\n"""
  header+=xml_content
  resp=self.send(header)
  if resp is None:
   self.view.print_("Pusta odpowiedz z serwera")
   return None,None,None,None
  try:
   resp_dict=self.soap.soap_xml_to_dict(resp)
   status=resp_dict['s:Envelope']['s:Body']['UploadTokenResponse']['UploadTokenResult']['a:status']
   if status!='Ok':
    self.view.print_("Blad(pobieranie informacji z chomika):")
    self.view.print_(status)
    return None,None,None,None
   token=resp_dict['s:Envelope']['s:Body']['UploadTokenResponse']['UploadTokenResult']['a:key']
   stamp=resp_dict['s:Envelope']['s:Body']['UploadTokenResponse']['UploadTokenResult']['a:stamp']
   server=resp_dict['s:Envelope']['s:Body']['UploadTokenResponse']['UploadTokenResult']['a:server']
   locale=resp_dict['s:Envelope']['s:Body']['UploadTokenResponse']['UploadTokenResult']['a:locale']
   server,_,port=server.partition(":")
   return token,stamp,server,port
  except Exception as e:
   self.view.print_("Blad parsowania odpowiedzi:",e)
   self.view.print_("Odpowiedz:",resp)
   return None,None,None,None
 def __upload(self,filepath,filename,token,stamp,server,port):
  size=os.path.getsize(filepath)
  header_bytes,contenttail_bytes=self.__create_header(server,port,token,stamp,filename,size)
  sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
  sock.settimeout(glob_timeout)
  ip=socket.gethostbyname_ex(server)[2][0]
  sock.connect((ip,int(port)))
  sock.send(header_bytes)
  f=open(filepath,'rb')
  pb=ProgressBar(total=size,rate_refresh=0.5,count=0,name=filepath)
  self.view.add_progress_bar(pb)
  last_time=time.time()
  try:
   while True:
    chunk=f.read(1024)
    if not chunk:break
    sock.send(chunk)
    pb.update(len(chunk))
    now=time.time()
    if now-last_time>0.5:
     self.view.update_progress_bars()
     last_time=now
   f.close()
   sock.send(contenttail_bytes)
  except Exception as e:
   if self.debug:
    trbck=sys.exc_info()[2]
    debug_fun(trbck)
   raise e
  finally:
   self.view.update_progress_bars()
   self.view.delete_progress_bar(pb)
  resp=b""
  while True:
   tmp=sock.recv(640)
   resp+=tmp
   if tmp==b''or b"/>"in resp:break
  sock.close()
  resp=resp.decode('utf-8',errors='ignore')
  if'<resp res="1" fileid='in resp:return True
  else:
   try:
    error_msg=re.findall(r'errorMessage="([^"]*)"',resp)[0]
    self.view.print_("BLAD(nieudane wysylanie):\r\n",error_msg)
   except IndexError:pass
   self.view.print_("Odpowiedz serwera:",resp)
   return False
 def __create_header(self,server,port,token,stamp,filename,size,resume_from=0):
  boundary="--!CHB"+str(stamp)
  filename_safe=str(filename).replace('"','\\"')
  contentheader=boundary+'\r\nContent-Disposition: form-data; name="chomik_id"\r\n\r\n'+str(self.chomik_id)+'\r\n'
  contentheader+=boundary+'\r\nContent-Disposition: form-data; name="folder_id"\r\n\r\n'+str(self.folder_id)+'\r\n'
  contentheader+=boundary+'\r\nContent-Disposition: form-data; name="key"\r\n\r\n'+str(token)+'\r\n'
  contentheader+=boundary+'\r\nContent-Disposition: form-data; name="time"\r\n\r\n'+str(stamp)+'\r\n'
  if resume_from>0:contentheader+=boundary+'\r\nContent-Disposition: form-data; name="resume_from"\r\n\r\n'+str(resume_from)+'\r\n'
  contentheader+=boundary+'\r\nContent-Disposition: form-data; name="client"\r\n\r\n'+client+'\r\n'
  contentheader+=boundary+'\r\nContent-Disposition: form-data; name="locale"\r\n\r\nPL\r\n'
  contentheader+=boundary+'\r\nContent-Disposition: form-data; name="file"; filename="'+filename_safe+'"\r\nContent-Type: application/octet-stream\r\n\r\n'
  contenttail='\r\n'+boundary+'--\r\n'
  contentheader_bytes=contentheader.encode('utf-8')
  contenttail_bytes=contenttail.encode('utf-8')
  contentlength=len(contentheader_bytes)+size+len(contenttail_bytes)
  header="POST /file/ HTTP/1.1\r\n"
  header+="Host: "+str(server)+":"+str(port)+"\r\n"
  header+="Content-Type: multipart/form-data; boundary="+boundary[2:]+"\r\n"
  header+="Content-Length: "+str(contentlength)+"\r\n"
  header+="Connection: close\r\n\r\n"
  header_bytes=header.encode('utf-8')+contentheader_bytes
  return header_bytes,contenttail_bytes
 def resume(self,filepath,filename,folder_id,chomik_id,token,server,port,stamp):
  self.relogin()
  self.chomik_id=chomik_id
  self.folder_id=folder_id
  filename_tmp=str(filename)
  filesize_sent=self.__resume_get_tokens(filepath,filename,token,server,port)
  if(filesize_sent==-1)or token==None:
   if self.debug:
    self.view.print_("Resume",filename_tmp)
    self.view.print_("Filesize sent",filesize_sent)
   return False
  else:return self.__resume_with_resume_option(filepath,filename,token,server,port,stamp,filesize_sent,chomik_id,folder_id)
 def __resume_with_resume_option(self,filepath,filename,token,server,port,stamp,filesize_sent,chomik_id,folder_id):
  try:
   result=self.__resume(filepath,filename,token,server,port,stamp,filesize_sent)
   self.view.print_("Result",result)
  except(socket.error,socket.timeout) as e:
   self.view.print_("Wznawianie\n")
   result=self.resume(filepath,filename,folder_id,chomik_id,token,server,port,stamp)
  return result
 def __resume_get_tokens(self,filepath,filename,token,server,port):
  sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
  sock.settimeout(glob_timeout)
  ip=socket.gethostbyname_ex(server)[2][0]
  sock.connect((ip,int(port)))
  tmp="""GET /resume/check/?key={0}& HTTP/1.1\r\nConnection: close\r\nUser-Agent: ChomikBox\r\nHost: {1}:{2}\r\n\r\n""".format(token,server,port)
  sock.send(tmp.encode('utf-8'))
  resp=b""
  while True:
   tmp=sock.recv(640)
   if tmp==b'':break
   resp+=tmp
  sock.close()
  resp=resp.decode('utf-8',errors='ignore')
  try:
   filesize_sent=int(re.findall(r'<resp file_size="([^"]*)" skipThumbnails="[^"]*" res="1"/>',resp)[0])
   return filesize_sent
  except IndexError as e:
   self.view.print_("Nie mozna bylo wznowic pobierania")
   self.view.print_(resp)
   return -1
 def __resume(self,filepath,filename,token,server,port,stamp,filesize_sent):
  size=os.path.getsize(filepath)
  header_bytes,contenttail_bytes=self.__create_header(server,port,token,stamp,filename,(size-filesize_sent),resume_from=filesize_sent)
  sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
  sock.settimeout(glob_timeout)
  ip=socket.gethostbyname_ex(server)[2][0]
  sock.connect((ip,int(port)))
  sock.send(header_bytes)
  f=open(filepath,'rb')
  f.seek(filesize_sent)
  pb=ProgressBar(total=size,rate_refresh=0.5,count=filesize_sent,name=filepath)
  self.view.add_progress_bar(pb)
  last_time=time.time()
  try:
   while True:
    chunk=f.read(1024)
    if not chunk:break
    sock.send(chunk)
    pb.update(len(chunk))
    now=time.time()
    if now-last_time>0.5:
     self.view.update_progress_bars()
     last_time=now
   f.close()
   sock.send(contenttail_bytes)
  except Exception as e:
   if self.debug:
    trbck=sys.exc_info()[2]
    debug_fun(trbck)
   raise e
  finally:
   self.view.update_progress_bars()
   self.view.delete_progress_bar(pb)
  resp=b""
  while True:
   tmp=sock.recv(640)
   resp+=tmp
   if tmp==b''or b"/>"in resp:break
  sock.close()
  resp=resp.decode('utf-8',errors='ignore')
  if'<resp res="1" fileid='in resp:return True
  else:
   try:
    error_msg=re.findall(r'errorMessage="([^"]*)"',resp)[0]
    self.view.print_("BLAD(nieudane wysylanie):\r\n",error_msg)
   except IndexError:pass
   self.view.print_(resp)
   return False
class UploaderThread(threading.Thread):
 def __init__(self,user,password,chomikpath,dirpath,view_,model_,debug=False):
  threading.Thread.__init__(self)
  self.uploader=Uploader(user,password,view_,model_,debug)
  self.chomikpath=chomikpath
  self.dirpath=dirpath
  self.daemon=True
 def run(self):
  self.uploader.upload_dir(self.chomikpath,self.dirpath)
class Uploader(object):
 def __init__(self,user=None,password=None,view_=None,model_=None,debug=False):
  if view_==None:self.view=View()
  else:self.view=view_
  if model_==None:self.model=Model()
  else:self.model=model_
  self.debug=debug
  self.user=user
  self.password=password
  self.notuploaded_file='notuploaded.txt'
  self.uploaded_file='uploaded.txt'
  self.chomik=Chomik(self.view,self.model,debug=self.debug)
  if self.user==None:self.user=input('Podaj nazwe uzytkownika:\n')
  if self.password==None:self.password=getpass.getpass('Podaj haslo:\r\n')
  self.view.print_('Logowanie')
  if not self.chomik.login(self.user,self.password):
   self.view.print_('Bledny login lub haslo')
   sys.exit(1)
 def upload_file(self,chomikpath,filepath):
  self.view.print_('Zmiana katalogow')
  self.chomik.chdirs(chomikpath)
  self.view.print_('Uploadowanie')
  try:result=self.chomik.upload(filepath,os.path.basename(filepath))
  except Exception as e:
   self.view.print_('Blad: ',e)
   if self.debug:
    trbck=sys.exc_info()[2]
    debug_fun(trbck)
   result=False
  if result==True:self.view.print_('Zakonczono uploadowanie')
  else:self.view.print_('Blad. Plik nie zostal wyslany')
 def upload_dir(self,chomikpath,dirpath):
  self.view.print_('Wznawianie nieudanych transferow')
  self.resume()
  self.view.print_('Zakonczono probe wznawiania transferow\r\n')
  self.view.print_('Zmiana katalogow')
  lock=self.model.return_chdirlock()
  lock.acquire()
  try:
   if not self.chomik.chdirs(chomikpath):
    self.view.print_('Nie udalo sie zmienic katalogu w chomiku',chomikpath)
    sys.exit(1)
  finally:lock.release()
  self.__upload_aux(dirpath)
  self.resume()
 def __upload_aux(self,dirpath):
  files=[i for i in os.listdir(dirpath)if os.path.isfile(os.path.join(dirpath,i))]
  files.sort()
  dirs=[i for i in os.listdir(dirpath)if os.path.isdir(os.path.join(dirpath,i))]
  dirs.sort()
  for fil in files:
   filepath=os.path.join(dirpath,fil)
   if not self.model.is_uploaded_or_pended_and_add(filepath):
    self.__upload_file_aux(fil,dirpath)
    self.model.remove_from_pending(filepath)
  for dr in dirs:
   address=self.chomik.cur_adr()
   self.__upload_dir_aux(dirpath,dr)
   self.chomik.cur_adr(address)
 def __upload_file_aux(self,fil,dirpath):
  filepath=os.path.join(dirpath,fil)
  self.view.print_('Uploadowanie pliku:',filepath)
  try:result=self.chomik.upload(filepath,os.path.basename(filepath))
  except Exception as e:
   self.view.print_('Blad:',e)
   self.view.print_('Blad. Plik ',filepath,' nie zostal wyslany\r\n')
   if self.debug:
    trbck=sys.exc_info()[2]
    debug_fun(trbck)
   return
  if result==False:self.view.print_('Blad. Plik ',filepath,' nie zostal wyslany\r\n')
  else:
   self.model.add_uploaded(filepath)
   self.model.remove_notuploaded(filepath)
   self.view.print_('Zakonczono uploadowanie\r\n')
 def __upload_dir_aux(self,dirpath,dr):
  lock=self.model.return_chdirlock()
  lock.acquire()
  try:changed=self.chomik.chdirs(dr)
  except Exception as e:
   self.view.print_('Blad. Nie wyslano katalogu: ',os.path.join(dirpath,dr))
   self.view.print_(e)
   if self.debug:
    trbck=sys.exc_info()[2]
    debug_fun(trbck)
   time.sleep(60)
   return
  finally:lock.release()
  if changed!=True:
   self.view.print_("Nie udalo sie zmienic katalogu",dr)
   return
  self.__upload_aux(os.path.join(dirpath,dr))
 def resume(self):
  notuploaded=self.model.get_notuploaded_resume()
  for filepath,filename,folder_id,chomik_id,token,host,port,stamp in notuploaded:
   if not self.model.is_uploaded_or_pended_and_add(filepath):
    self.__resume_file_aux(filepath,filename,folder_id,chomik_id,token,host,port,stamp)
    self.model.remove_from_pending(filepath)
 def __resume_file_aux(self,filepath,filename,folder_id,chomik_id,token,host,port,stamp):
  self.view.print_('Wznawianie pliku:',filepath)
  try:result=self.chomik.resume(filepath,filename,folder_id,chomik_id,token,host,port,stamp)
  except Exception as e:
   self.view.print_('Blad:',e)
   if self.debug:
    trbck=sys.exc_info()[2]
    debug_fun(trbck)
   self.view.print_('Blad. Plik ',filepath,' nie zostal wyslany\r\n')
   return False
  if result==False:
   self.view.print_('Blad. Plik ',filepath,' nie zostal wyslany\r\n')
   return False
  else:
   self.model.add_uploaded(filepath)
   self.model.remove_notuploaded(filepath)
   self.view.print_('Zakonczono uploadowanie\r\n')
   return True
 def upload_multi(self,chomikpath,dirpath,n):
  th=[]
  for i in range(n):
   upl=UploaderThread(self.user,self.password,chomikpath,dirpath,view_=self.view,model_=self.model,debug=self.debug)
   upl.start()
  while threading.active_count()>1:time.sleep(1.)
def usage():
 print('Użycie:')
 print('python',sys.argv[0],'[-h] [-l login] [-p hasło] [-r katalog_chomik katalog_dysk] [-u katalog_chomik plik]')
 print('-h pomoc -r rekurencyjnie -u upload -l login -p hasło -d debug -t wątki')
if True:
 try:
  opts,args=getopt.getopt(sys.argv[1:],'hrul:p:dt:',['help','recursive','upload','login','password','debug','threads'])
 except Exception as e:
  print('Niepoprawny parametr')
  print(e)
  usage()
  sys.exit(2)
 if opts==[]:usage()
 login=password=None
 threads=1
 debug=False
 for opt,arg in opts:
  if opt in('-h','--help'):
   usage()
   sys.exit()
  elif opt in('-l','--login'):login=arg
  elif opt in('-p','--password'):password=arg
  elif opt in('-t','--threads'):threads=int(arg)
  elif opt in('-d','--debug'):debug=True
 try:
  for opt,arg in opts:
   if opt in('-r','--recursive'):
    chomik_path,dirpath=args
    u=Uploader(login,password,debug=debug)
    if threads>1:u.upload_multi(chomik_path,dirpath,threads)
    else:u.upload_dir(chomik_path,dirpath)
   elif opt in('-u','--upload'):
    chomik_path,filepath=args
    u=Uploader(login,password,debug=debug)
    u.upload_file(chomik_path,filepath)
 except ValueError as e:
  print(e)
  print("Błąd: Musisz podać scieżkę na chomiku i dysku")
