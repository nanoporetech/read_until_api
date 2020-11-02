Read Until
==========

Adaptive sampling enables a large number of applications, traditionally associated with complex 
molecular biology methods, to be carried out by the sequencer itself.  Adaptive sampling enables 
the following: 

**Enrichment**:  Users can ask the system to enrich for strands that contain a target region of interest, a 
haplotype of choice or an organism of interest against a complex background 

**Depletion**: Users can reject strands from an organism which is of no interest (e.g. host depletion).
In the case of pathogen detection or microbiome applications in human health this could be enabled as a 
"human filter" ensuring that this sensitive, confidential data is never committed to disk.

**Balancing**: Users can use adaptive sampling to balance their barcodes, ensuring they achieve target 
depths for each barcode and also even out coverage across a genome by rejecting strands representing 
regions of the genome already at their target depth in favour of regions that have lower coverage.

The read until API is provided "as is" as a research tool. Issue reporting has been disabled on the 
github website; users with questions should go to the Nanopore community and post comments 
[here](https://community.nanoporetech.com/posts/adaptive-sampling-release). Usage currently requires 
some advanced programming capability. Efforts are ongoing by the Oxford Nanopore team to release simpler 
versions of this tool enabling more and more users to deploy it successfully.

Please add new feature requests to the 
[feature request pinboard](https://community.nanoporetech.com/posts/ideas-and-suggestions-port) under the 
tag "Adaptive Sampling".

The Read Until API provides a mechanism for an application to connect to a
MinKNOW server to obtain read data in real-time. The data can be analysed in the
way most fit for purpose, and a return call can be made to the server to unblock
the read in progress.


![Read Until Example](read_until.gif "Read Until example")

Installation
------------

The client requires MinKNOW-Core 4.0 or later.

The package can be installed into a python virtual environment e.g.:

```shell script
python3 -m venv read_until_venv
source read_until_venv/bin/activate

pip install git+https://github.com/nanoporetech/read_until_api@master
```

Installation of the package into other python environments is supported. The project
contains everything it needs to communicate with MinKNOW over a network.

Two demonstration programs are provided:

   1.  `read_until_simple`: this serves as a simple test, and the code
       (module `read_until.simple`) demonstrates use of basic functionality
       for developers.
   2.  `read_until_ident`: this is a more fully featured example, using
       the API to identify reads via basecalling and alignment. To run it
       requires the optional dependency `ont-pyguppy-client-lib` (https://pypi.org/project/ont-pyguppy-client-lib/).

Client Overview
---------------

The python Read Until package provides a high level interface to requisite parts
of MinKNOW's [gRPC](https://grpc.io/) interface. Developer's can focus on
creating rich analyses, rather than the lower level details of handling the data
that MinKNOW provides. The purpose of the read until functionality is to
selectively, based on any conceivable analysis, "unblock" sequencing channels
to increases the time spent sequencing analytes of interest. MinKNOW can be
requested to send a continuous stream of "read chunks" (of a configurable
minimum size), which the client can analyse.

The main client code is located in the `read_until.base.ReadUntilClient` class,
which can be imported as simply:

    from read_until import ReadUntilClient

The interface to this class is thoroughly documented, with additional comments
throughout for developers who wish to develop their own custom client from the
gRPC stream. Developers are encouraged to read the code and inline documentation.

The gRPC stream managed by the client is bidirectional: it carries both raw data
"read chunks" to the client and "action responses" to MinKNOW. The client
implements two queues. The first is the `.action_queue` and is fairly
straight-forward: requests to MinKNOW to unblock channels are temporarily stored
here, bundled together and then dispatched.

The second queue is more elaborate, it is implemented in
`read_until.read_cache.ReadCache`. The client stores read chunks here in preparation
for analysis. The queue is additionally keyed on channel such that it only ever
stores a single chunk from each sequencer channel; thereby protecting consumers
of the client from reads which have already ended. An extended cache `AccumulatingCache`
is also provided in `read_until.read_cache` that combines raw data chunks from the 
same read. Developers should read the code and comments in the to better understand how 
these caches work.

For many developers the details of these queues may be unimportant, at least in
getting started. Of more immediate importance are several methods of the
`ReadUntilClient` class:

*`.run()`*
instruct the class to start retrieving read chunks from MinKNOW.

*`.get_read_chunks()`*
obtain the most recent data retrieved from MinKNOW.

*`.unblock_read()`*
request that a read be ejected from a channel.

*`.stop_receiving_read()`*
request that no more data for a read be sent to the client by MinKNOW. It is not
guaranteed that further data will not be sent, and in the general case the
client does not filter subsequent data from its consumers (although when the
client is created with the `one_chunk` option, the client will provide
additional filtering of the data received from MinKNOW).

Examples of use of the client are given in the codebase, but most simply can be
reduced to:

```python
from concurrent.futures import ThreadPoolExecutor
import numpy
from read_until import ReadUntilClient

def analysis(client, *args, **kwargs):
    while client.is_running:
        for channel, read in client.get_read_chunks():
            raw_data = numpy.frombuffer(read.raw_data, client.signal_dtype)
            # do something with raw data... and maybe call:
            #    client.stop_receiving_read(channel, read.number)
            #    client.unblock_read(channel, read.number)

read_until_client = ReadUntilClient()
read_until_client.run()
with ThreadPoolExecutor() as executor:
    executor.submit(analysis, read_until_client)
```

Extending the client
--------------------

The `ReadUntilClient` class has been implemented to provide an abstraction which
does not require an in-depth knowledge of the MinKNOW gRPC interface. To extend
the client however some knowledge of the messages passed between MinKNOW and a
client is required. Whilst the provided client shows how to construct and decode
basic messages, the following (an extract from Protocol Buffers definition
files) serves as a more complete reference.

**Messages sent from a client to MinKNOW**

```protobuf
message GetLiveReadsRequest {
    enum RawDataType {
        // Don't change the previously specified setting for raw data sent with live reads
        // note: If sent when there is no last setting, NONE is assumed.
        KEEP_LAST = 0;
        // No raw data required for live reads
        NONE = 1;
        // Calibrated raw data should be sent to the user with each read
        CALIBRATED = 2;
        // Uncalibrated data should be sent to the user with each read
        UNCALIBRATED = 3;
    }

    message UnblockAction {
        // Duration of unblock in seconds.
        double duration = 1;
    }

    message StopFurtherData {}

    message Action {
        string action_id = 1;
        // Channel name to unblock
        uint32 channel = 2;

        // Identifier for the read to act on.
        //
        // If the read requested is no longer in progress, the action fails.
        oneof read {
            string id = 3;
            uint32 number = 4;
        }

        oneof action {
            // Unblock a read and skip further data from this read.
            UnblockAction unblock = 5;

            // Skip further data from this read, doesn't affect the read data.
            StopFurtherData stop_further_data = 6;
        }
    }

    message StreamSetup {
        // The first channel (inclusive) to return data for.
        //
        // Note that channel numbering starts at 1.
        uint32 first_channel = 1;

        // The last channel (inclusive) to return data for.
        //
        // Note that channel numbering starts at 1.
        uint32 last_channel = 2;

        // Specify the type of raw data to retrieve
        RawDataType raw_data_type = 3;

        // Minimum chunk size read data is returned in.
        uint64 sample_minimum_chunk_size = 4;
    }

    message Actions {
        repeated Action actions = 2;
    }

    oneof request {
        // Read setup request, initialises channel numbers and type of data returned.
        //
        // note: Must be specified in the first message sent to MinKNOW. Once MinKNOW
        // has the first setup message reads are sent to the caller as requested.
        // The user can then resend a setup message as frequently as they need to in order
        // to reconfigure live reads - for example by changing if raw data is sent with
        // reads or not.
        StreamSetup setup = 1;

        // Actions to take given data returned to the user - can only be sent once the setup
        // message above has been sent.
        Actions actions = 2;
    }
}
```

**Messages received by a client from MinKNOW**

```protobuf
message GetLiveReadsResponse {
    message ReadData {
        // The id of this read, this id is unique for every read ever produced.
        string id = 1;

        // The minknow assigned number of this read
        //
        // Read numbers always increment throughout the experiment, and are unique per channel -
        // however they are not necessarily contiguous.
        uint32 number = 2;

        // Absolute start point of this read
        uint64 start_sample = 3;

        // Absolute start point through the experiment of this chunk
        uint64 chunk_start_sample = 4;

        // Length of the chunk in samples
        uint64 chunk_length = 5;

        // All Classifications given to intermediate chunks by analysis
        //
        // See analysis_configuration.get_read_classifications for how to map these integers to names.
        repeated int32 chunk_classifications = 6;

        // Any raw data selected by the request
        //
        // The type of the elements will depend on whether calibrated data was chosen. The
        // get_data_types() RPC call should be used to determine the precise format of the data, but
        // in general terms, uncalibrated data will be signed integers and calibrated data will be
        // floating-point numbers.
        bytes raw_data = 7;

        // The median of the read previous to this read.
        // intended to allow querying of the approximate level of this read, comapred to the last.
        //
        // For example, a user could try to verify this is a strand be ensuring the median of the
        // current read is lower than the median_before level.
        float median_before = 8;

        // The media pA level of this read from all aggregated read chunks so far.
        float median = 9;
    };

    message ActionResponse {
        string action_id = 1;

        enum Response {
            SUCCESS = 0;
            FAILED_READ_FINISHED = 1;
        }

        Response response = 2;
    }

    // The number of samples collected before the first sample included in this response.
    //
    // This gives the position of the first data point on each channel in the overall stream of data
    // being acquired from the device (since this period of data acquisition was started).
    uint64 samples_since_start = 1;

    // The number of seconds elapsed since data acquisition started.
    //
    // This is the same as ``samples_since_start``, but expressed in seconds.
    double seconds_since_start = 2;

    // In progress reads for the requested channels.
    //
    // Sparsely populated as not all channels have new/incomplete reads.
    map<uint32, ReadData> channels = 4;

    // List of repsonses to requested actions, informing the caller of results to requested
    // unblocks or discards of data.
    repeated ActionResponse action_responses = 5;
}
```
