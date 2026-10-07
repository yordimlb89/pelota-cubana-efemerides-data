"""Deterministic thresholds copied from the reviewed site detector."""
def number(s,key):
 try:return int(s[key])
 except (KeyError,ValueError,TypeError):return None

def achievements(s,post=False):
 out=[]
 hr,h,ab,d,t,rbi=(number(s,k) for k in ['homeRuns','hits','atBats','doubles','triples','rbi'])
 if hr is not None and hr>=(2 if post else 3):out.append(f'{hr} jonrones en un juego')
 if s.get('group')!='pitching' and h is not None and h>=5:out.append(f'{h} hits en un juego')
 if rbi is not None and rbi>=7:out.append(f'{rbi} carreras impulsadas en un juego')
 if None not in [h,d,t,hr] and min(d,t,hr)>=1 and h-d-t-hr>=1:out.append('Batea para el ciclo')
 k=number(s,'strikeOuts')
 if s.get('group')=='pitching' and k is not None and k>=15:out.append(f'{k} ponches en un juego')
 # Never infer a complete no-hitter or perfect game from an individual zero-hit relief line.
 if s.get('group')=='pitching' and s.get('completeGame') and s.get('inningsPitched')=='9.0' and h==0:out.append('Juego completo de nueve entradas sin hits')
 return out

