#!/bin/bash

mkdir -p server/proto_generated
protoc -I=server/proto --python_out=server/proto_generated --pyi_out=server/proto_generated tts.proto health.proto
pbjs -t static server/proto/tts.proto > frontend/generated/tts_pb.js