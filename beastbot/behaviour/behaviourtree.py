from rlbot.agents.base_agent import SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket


SUCCESS = 0
FAILURE = 1
EVALUATING = 2 # always goes downwards in tree
ACTION = 3


class BTNode:
	def __init__(self, children=[]):
		self.parent = None
		self.children = []
		for child in children:
			self.add_child(child)
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		# Here the node will calculate and do stuff
		# Returns a tuple (int, BTNode, SimpleControllerState)
		# - status
		# - the next node to be called (eg. parent, or child)
		# - a controller state (only when status == ACTION)
		# Remember to reset when nercessary
		pass
		
	def add_child(self, child):
		self.children.append(child)
		child.parent = self
		
	def reset(self):
		pass


class BehaviourTree:
	def __init__(self, node):
		self.root = node
		self.current = node
	
	def resolve(self, car, packet: GameTickPacket) -> SimpleControllerState:
		if self.current:
			
			# Evaluate until an action is found
			val = self.current.resolve(ACTION, car, packet)
			while val[0] != ACTION:
				
				self.current = val[1]
				if self.current == None:
					# We have reached the root, do nothing but start from root next time
					self.current = self.root
					self.root.reset()
					return SimpleControllerState()
					
				val = self.current.resolve(val[0], car, packet)
			
			self.current = val[1]
			controller_state = val[2]
			return controller_state
			
		print("ERROR: BT.current is None")
		return SimpleControllerState()
	
	def reset(self):
		self.current.reset()
		self.current == self.root


# ========================== Composite Nodes =========================================================================


# Sequencer, aborts on failure by returning failure
class Sequencer(BTNode):
	def __init__(self, children = []):
		super().__init__(children)
		self.next = -1
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		child_count = len(self.children)
		if child_count <= 0:
			print("ERROR: Sequencer has no children!")
		
		# abort
		if prev_status == FAILURE:
			self.reset()
			return (FAILURE, self.parent, None)
		
		# prev must have be success, action or evaluating
		# resolve next
		self.next += 1
		if self.next < child_count:
			return (EVALUATING, self.children[self.next], None)
		else:
			# out of children, all succeeded!
			self.reset()
			return (SUCCESS, self.parent, None)
			
	def reset(self):
		self.next = -1


# Selector, aborts on success by returning success
class Selector(BTNode):
	def __init__(self, children=None):
		super().__init__(children)
		if children is None:
			children = []
		self.next = -1
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		child_count = len(self.children)
		if child_count <= 0:
			print("ERROR: Selector has no children!")
		
		# abort
		if prev_status == SUCCESS or prev_status == ACTION:
			self.reset()
			return (SUCCESS, self.parent, None)
		
		# prev must have be failure or evaluating
		# resolve next
		self.next += 1
		if self.next < child_count:
			return (EVALUATING, self.children[self.next], None)
		else:
			# out of children, all failed!
			self.reset()
			return (FAILURE, self.parent, None)
	
	def reset(self):
		self.next = -1


# ========================== Decorator Nodes =========================================================================


# sig: <task>
class Inverter(BTNode):
	def __init__(self, child):
		super().__init__([child])
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		if prev_status == EVALUATING:
			return (EVALUATING, self.children[0], None)
		elif prev_status == FAILURE:
			return (SUCCESS, self.parent, None)
		else:
			return (FAILURE, self.parent, None)


# Returns SUCCESS when done
# sig: <x:int> <task>
class RepeatXTimes(BTNode):
	def __init__(self, x, child):
		super().__init__([child])
		self.x = x
		self.count = 0
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		if self.count < self.x:
			self.count += 1
			return (EVALUATING, self.children[0], None)
		else:
			self.reset()
			return (SUCCESS, self.parent, None)
	
	def reset(self):
		self.count = 0


# Returns FAILURE after X tries without child return SUCCESS or ACTION
# sig: <x:int> <task>
class TryXTimes(BTNode):
	def __init__(self, x, child):
		super().__init__([child])
		self.x = x
		self.count = 0
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		if prev_status == ACTION or prev_status == SUCCESS:
			self.reset()
			return (SUCCESS, self.parent, None)
		elif self.count < self.x:
			self.count += 1
			return (EVALUATING, self.children[0], None)
		else:
			self.reset()
			return (FAILURE, self.parent, None)
	
	def reset(self):
		self.count = 0


# Returns SUCCESS when done
# sig: <task>
class RepeatUntilFailure(BTNode):
	def __init__(self, child):
		super().__init__([child])
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		if prev_status != FAILURE:
			return (EVALUATING, self.children[0], None)
		else:
			return (SUCCESS, self.parent, None)


# Returns SUCCESS when done
# sig: <task>
class RepeatUntilSuccess(BTNode):
	def __init__(self, child):
		super().__init__([child])
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		if prev_status != SUCCESS and prev_status != ACTION:
			return (EVALUATING, self.children[0], None)
		else:
			return (SUCCESS, self.parent, None)


# sig: <task>
class AlwaysFailure(BTNode):
	def __init__(self, child):
		super().__init__([child])
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		if prev_status == EVALUATING:
			return (EVALUATING, self.children[0], None)
		return (FAILURE, self.parent, None)


# sig: <task>
class AlwaysSuccess(BTNode):
	def __init__(self, child):
		super().__init__([child])
	
	def resolve(self, prev_status, car, packet: GameTickPacket):
		if prev_status == EVALUATING:
			return (EVALUATING, self.children[0], None)
		return (SUCCESS, self.parent, None)