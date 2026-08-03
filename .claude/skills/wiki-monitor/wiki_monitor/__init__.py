"""Pure-Python core of the weekly Salmonella Wiki Monitor.

Everything in this package is deterministic: no network calls, no LLM
invocation.  The source adapters and the email send sit outside it.
"""
