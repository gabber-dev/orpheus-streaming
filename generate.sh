#!/bin/bash

mkdir -p server/proto_generated
protoc -I=proto --python_out=proto_generated --pyi_out=proto_generated tts.proto health.proto
touch proto_generated/__init__.py
pbjs -t static proto/tts.proto > frontend/generated/tts_pb.js