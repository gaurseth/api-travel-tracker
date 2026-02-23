# Example API Response with Confidence Aggregation

## Endpoint: POST /extract-boarding-pass

### Example Response Structure

```json
{
  "boarding_pass": {
    "passenger": {
      "full_name": {
        "value": "SETH GAURAV",
        "confidence": 0.92,
        "confidence_factors": null
      },
      "first_name": {
        "value": "GAURAV",
        "confidence": 0.92,
        "confidence_factors": {
          "ocr": 1.0,
          "pattern": 1.0,
          "context": 0.9,
          "airline": 0.0
        }
      },
      "last_name": {
        "value": "SETH",
        "confidence": 0.92,
        "confidence_factors": {
          "ocr": 1.0,
          "pattern": 1.0,
          "context": 0.9,
          "airline": 0.0
        }
      }
    },
    "flight": {
      "flight_number": {
        "value": "231",
        "confidence": 0.93,
        "confidence_factors": {
          "ocr": 1.0,
          "pattern": 1.0,
          "context": 0.8,
          "airline": 1.0
        }
      },
      "airline_code": {
        "value": "EK",
        "confidence": 0.93,
        "confidence_factors": {
          "ocr": 1.0,
          "pattern": 1.0,
          "context": 0.8,
          "airline": 1.0
        }
      },
      "operating_carrier": null,
      "date": {
        "value": "2026-02-14",
        "confidence": 0.88,
        "confidence_factors": {
          "ocr": 1.0,
          "pattern": 0.95,
          "context": 0.85,
          "airline": 0.8
        }
      }
    },
    "airline": null,
    "route": {
      "origin": {
        "iata": {
          "value": "DXB",
          "confidence": 0.95,
          "confidence_factors": {
            "ocr": 1.0,
            "pattern": 1.0,
            "context": 0.95,
            "airline": 0.85
          }
        },
        "city": null
      },
      "destination": {
        "iata": {
          "value": "IAH",
          "confidence": 0.95,
          "confidence_factors": {
            "ocr": 1.0,
            "pattern": 1.0,
            "context": 0.95,
            "airline": 0.85
          }
        },
        "city": null
      }
    },
    "boarding": {
      "time": {
        "value": "10:40",
        "confidence": 0.91,
        "confidence_factors": {
          "ocr": 1.0,
          "pattern": 0.95,
          "context": 0.9,
          "airline": 0.85
        }
      },
      "gate": {
        "value": "C14",
        "confidence": 0.92,
        "confidence_factors": {
          "ocr": 1.0,
          "pattern": 0.95,
          "context": 0.95,
          "airline": 0.85
        }
      },
      "seat": {
        "value": "22A",
        "confidence": 0.90,
        "confidence_factors": {
          "ocr": 1.0,
          "pattern": 0.95,
          "context": 0.75,
          "airline": 0.9
        }
      },
      "group": null
    },
    "pnr": {
      "value": "A7K9PZ",
      "confidence": 0.87,
      "confidence_factors": {
        "ocr": 1.0,
        "pattern": 0.9,
        "context": 0.85,
        "airline": 0.75
      }
    },
    "sequence_number": null,
    "barcode": null,
    "raw_ocr_text": "..."
  },
  "extraction_metadata": {
    "overall_confidence": 0.91,
    "quality": "excellent",
    "warnings": [],
    "method": "rules"
  },
  "raw_text": "BOARDING PASS\nSETH/GAURAV MR\nEK 231\nDXB TO IAH\n14 FEBRUARY\nBOARDING: 10:40\nGATE: C14\nSEAT: 22A\nPNR: A7K9PZ\n..."
}
```

## Confidence Scoring System

### Field Weights (for overall confidence)
- Passenger Name: 20%
- Flight Number: 20%
- Date: 15%
- Route: 15%
- Seat: 8%
- Gate: 7%
- Boarding Time: 5%
- PNR: 10%

### Quality Labels
- **excellent** (≥ 0.90): High accuracy, auto-accept
- **good** (0.75-0.89): Acceptable, optional review
- **medium** (0.60-0.74): Triggers AI fallback
- **low** (< 0.60): Manual review required

### Warnings
Warnings are generated for:
- Missing critical fields (passenger, flight, date, route)
- Low confidence fields (< 0.75 for critical, < 0.70 for optional)

Example warnings:
```json
"warnings": [
  {
    "field": "pnr",
    "reason": "Low confidence PNR extraction",
    "confidence": 0.62
  },
  {
    "field": "date",
    "reason": "Flight date not found",
    "confidence": 0.0
  }
]
```

## Next Steps
- Add AI fallback when `overall_confidence < 0.75`
- Add DocumentEnvelope with user_id and tenant_id
- Implement persistence layer
