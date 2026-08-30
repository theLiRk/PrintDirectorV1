import heapq
class EventQueue:
 def __init__(self): self._q=[]
 def push(self,e): heapq.heappush(self._q,e)
 def pop(self): return heapq.heappop(self._q) if self._q else None
 def __len__(self): return len(self._q)
