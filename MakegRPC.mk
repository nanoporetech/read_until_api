SEDI=sed -i
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
	SEDI=sed -i '.bak'
endif

VENV=rpc_venv
venv: ${VENV}/bin/activate
IN_VENV=. ./${VENV}/bin/activate

${VENV}/bin/activate:
	test -d ${VENV} || virtualenv ${VENV} --python=python3
	${IN_VENV} && pip install pip --upgrade
	${IN_VENV} && pip install protobuf
	${IN_VENV} && pip install grpcio
	${IN_VENV} && pip install grpcio-tools

clean:
	rm -rf ${VENV} ${OUTDIR} protobuff minknow/rpc/*_pb2* tmp

build: clean venv
	git clone https://git.oxfordnanolabs.local/minknow/protobuff
	# Google intends that the .proto files should live where their generated
	#   files are to be imported and that they correctly use package names. We
	#   don't have this so we need to jump through a few hoops
	mkdir protobuff/minknow/rpc && mv protobuff/minknow/*.proto protobuff/minknow/rpc
	mkdir tmp
	${IN_VENV} && python -m grpc_tools.protoc -I ./protobuff/minknow/rpc --proto_path=./protobuff --python_out=tmp --grpc_python_out=tmp ./protobuff/minknow/rpc/*.proto
	./change_imports.sh
	cp tmp/*pb2*.py minknow/rpc

	#${IN_VENV} && python -m grpc_tools.protoc --proto_path=.protobuf --python_out=. --grpc_python_out=. minknow/analysis_configuration.proto data.proto device.proto instance.proto keystore.proto log.proto minion_device.proto production.proto promethion_device.proto protocol.proto reads.proto rpc_options.proto
	#cp -r protobuff/minknow/pyrpc/*_pb2* minknow/rpc/
