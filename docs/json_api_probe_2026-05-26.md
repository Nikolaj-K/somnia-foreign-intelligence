# JsonApiUintProbe Report

Date: 2026-05-26

## Deployment

- Network: Somnia Shannon testnet
- Probe contract: `0x535A56B754e705ab251cD89C4Aa43e62c5F27B3F`
- Deploy transaction:
  `0x46b3f29e3ca1f205ac96e32169c7f8e5743f730ee2e44340f8fec09a4a8a744e`

## Probe Request

- Request transaction:
  `0xdf9bd33e83e73f2d8e3793c25745d5f9d43789e17b362c617f179459e9396e53`
- Request ID: `2278035`
- Request value: `0.12 STT`
- Public wrapper URL:
  `https://somnia-ownership-wrapper-735868209397.europe-west1.run.app/owns?wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>`

## JSON API Settings

```text
agent_id=13174292974160097713
method=fetchUint(string,string,uint8)
selector=0x3bbc1302
selector_path=ownsInt
decimals=0
```

## Successful Probe Read

```text
last_request_id=2278035
last_status=2
last_decode_ok=True
last_decoded_uint=1
last_raw_result=0x0000000000000000000000000000000000000000000000000000000000000001
pending=False
```

## Interpretation

The official Somnia JSON API agent successfully fetched the Cloud Run wrapper,
selected `ownsInt`, and returned ABI-encoded `uint256` value `1`. The voting
contract should only be used after this condition holds.
