import numpy as np
from abc import ABCMeta, abstractmethod

class Activation(metaclass=ABCMeta):

	def __init__(self):
		pass

	@abstractmethod
	def __call__(self, x):
		pass

	# @abstractmethod
	# def __str__(self):
	# 	return "Activation"

	@abstractmethod
	def derivate(self, x):
		pass