from paperflow.classifier_v2 import signal_text, source_tag
from paperflow.metadata import enrich_item
from paperflow.models import ZoteroItem


def _enriched_item(
    doi: str | None = None,
    url: str | None = None,
    item_type: str = "journalArticle",
    publication_title: str | None = None,
):
    return enrich_item(
        ZoteroItem(
            key="TEST",
            item_type=item_type,
            title="A Test Paper",
            doi=doi,
            url=url,
            publication_title=publication_title,
            abstract_note="Abstract.",
        )
    )


def test_elsevier_doi_numeric_fragment_does_not_produce_arxiv_id() -> None:
    item = _enriched_item(doi="10.1016/j.jpowsour.2021.230024")

    assert item.arxiv_id is None


def test_ieee_doi_numeric_fragment_does_not_produce_arxiv_id() -> None:
    item = _enriched_item(doi="10.1109/CVPR52688.2022.01631")

    assert item.arxiv_id is None


def test_arxiv_doi_produces_arxiv_id() -> None:
    item = _enriched_item(doi="10.48550/arXiv.2505.07817")

    assert item.arxiv_id == "2505.07817"


def test_arxiv_abs_url_produces_arxiv_id() -> None:
    item = _enriched_item(url="http://arxiv.org/abs/2210.03117")

    assert item.arxiv_id == "2210.03117"


def test_ieee_conference_without_arxiv_url_gets_source_conference() -> None:
    item = _enriched_item(
        doi="10.1109/CVPR52688.2022.01631",
        item_type="conferencePaper",
        publication_title="CVPR",
    )

    assert source_tag(item, signal_text(item)) == "source/conference"
    assert source_tag(item, signal_text(item)) != "source/arxiv"


def test_ieee_conference_item_type_without_arxiv_url_gets_source_conference() -> None:
    item = _enriched_item(
        doi="10.1109/WACV57701.2024.00567",
        item_type="conferencePaper",
        publication_title="IEEE/CVF Winter Conference on Applications of Computer Vision",
    )

    assert source_tag(item, signal_text(item)) == "source/conference"
    assert source_tag(item, signal_text(item)) != "source/arxiv"


def test_elsevier_journal_without_arxiv_url_gets_source_journal() -> None:
    item = _enriched_item(
        doi="10.1016/j.jpowsour.2021.230024",
        item_type="journalArticle",
        publication_title="Journal of Power Sources",
    )

    assert source_tag(item, signal_text(item)) == "source/journal"
    assert source_tag(item, signal_text(item)) != "source/arxiv"
