#!/usr/bin/env python3
import aws_cdk as cdk

from takehome_stack.takehome_stack import TakehomeStack

app = cdk.App()
TakehomeStack(app, "SixthStreetTakehomeStack")

app.synth()
