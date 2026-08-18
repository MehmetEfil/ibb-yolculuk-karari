"""
Veri modelleri.

Orijinal panelde burada bir SQLAlchemy tablosu (YolculukGecmisi → yerel MSSQL)
da vardı. Bu projede kaldırıldı: hiçbir canlı uç kullanmıyordu ve yerel
SQL Server bağımlılığı deploy'u imkânsız kılıyordu.
"""
from dataclasses import dataclass


@dataclass
class TrafficIndexHistoryItem:
    traffic_index: int
    traffic_index_date: str
    period: str = ""
    source: str = "ibb_traffic"

    def to_dict(self):
        return {
            "traffic_index": self.traffic_index,
            "traffic_index_date": self.traffic_index_date,
            "period": self.period,
            "source": self.source,
        }
