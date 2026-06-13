"""Campaign Intelligence Engine — unified keyword + hook generation.

One engine, two generation tracks (``keywords`` and ``creatives``) sharing a
single learning spine (``shared``). The domain layer here imports nothing from
``infrastructure`` and contains only pure logic — value objects, entities, and
deterministic services. See ``docs`` and the module docstrings for the design.
"""
