"""One module per step, each importing only the context and the behaviour layer.

Steps never import each other. That is what makes them individually readable and
individually replaceable - the order lives in pipeline.py and nowhere else.
"""
