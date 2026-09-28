"""LiveKit stub compiles and satisfies RealtimeTransport."""

import pytest

from relay_adapter_realtime_pipecat import LiveKitRealtimeTransport


@pytest.mark.asyncio
async def test_livekit_stub_not_implemented():
    transport = LiveKitRealtimeTransport()
    assert not await transport.is_connected("s1")
    with pytest.raises(NotImplementedError):
        await transport.connect("s1", offer={"sdp": "v=0", "type": "offer"})
