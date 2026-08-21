"""Canonical entity identity.

Everything upstream of this package joins on names.  That is how one human ends
up as several ``players`` rows with their match history split between them --
measured on 2026-08-09: 864 normalised names held more than one row, 1,026 of
those rows appeared in real fixtures, and 3,057 history rows sat on a duplicate
id.  Since the ace model refuses a player with fewer than ten prior matches, a
player split 70/8/0 across three ids can be rejected as "too thin to model"
while the data is right there under another id.
"""
