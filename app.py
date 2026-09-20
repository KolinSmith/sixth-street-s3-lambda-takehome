#!/usr/bin/env python3
import aws_cdk as cdk

# Import our stack class from takehome_stack/takehome_stack.py. "takehome_stack.takehome_stack"
# means: the takehome_stack/ folder (a Python package, marked by its __init__.py), then the
# takehome_stack.py file inside it, then the TakehomeStack class defined there.
from takehome_stack.takehome_stack import TakehomeStack

# cdk.App() is the root of everything CDK builds. Every stack you define gets attached to it.
app = cdk.App()

# Instantiate our one stack. "SixthStreetTakehomeStack" is the actual CloudFormation stack
# name that will show up in the AWS Console — everything in takehome_stack.py (the bucket,
# the Lambda, the policy) gets created under this one named stack.
TakehomeStack(app, "SixthStreetTakehomeStack")

# Turns the Python objects above into a CloudFormation template (JSON/YAML) that AWS
# actually understands. This is what `cdk synth` and `cdk deploy` both run under the hood —
# synth stops here and just prints the template; deploy does this too, then sends it to AWS.
app.synth()
