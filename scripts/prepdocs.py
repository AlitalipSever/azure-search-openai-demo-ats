import argparse
import html
import io
import re
import time
from azure.identity import AzureDeveloperCliCredential
from azure.core.credentials import AzureKeyCredential
from azure.storage.blob import BlobServiceClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import *
from azure.search.documents import SearchClient
from contentful import Client

MAX_SECTION_LENGTH = 1000
SENTENCE_SEARCH_LIMIT = 100
SECTION_OVERLAP = 100

parser = argparse.ArgumentParser(
    description="Prepare documents by extracting content from Contentful, splitting content into sections, uploading to blob storage, and indexing in a search index.",
    epilog="Example: prepdocs.py --space <contentful-space> --environment <contentful-environment> --contenttype <contentful-contenttype> --field <contentful-field> --storageaccount <storage-account> --container <blob-container> --searchservice <search-service> --index <search-index> -v"
)
parser.add_argument("--space", required=True, help="Contentful space ID")
parser.add_argument("--environment", required=True, help="Contentful environment ID")
parser.add_argument("--contenttype", required=True, help="Contentful content type ID")
parser.add_argument("--field", required=True, help="Contentful field name containing the text data")
parser.add_argument("--storageaccount", required=True, help="Azure Blob Storage account name")
parser.add_argument("--container", required=True, help="Azure Blob Storage container name")
parser.add_argument("--searchservice", required=True, help="Azure Cognitive Search service name")
parser.add_argument("--index", required=True, help="Azure Cognitive Search index name")
parser.add_argument("--searchkey", required=True, help="Azure Cognitive Search account key")
parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
args = parser.parse_args()


def fetch_data_from_contentful():
    space_id = "<your-contentful-space-id>"
    environment_id = "<your-contentful-environment-id>"
    content_type_id = "<your-contentful-content-type-id>"
    field_name = "<your-contentful-field-name>"

    # Create a Contentful client
    client = Client(
        space_id=space_id,
        environment_id=environment_id,
        access_token="<your-contentful-access-token>"
    )

    # Fetch entries from Contentful based on the specified content type
    entries = client.entries({
        'content_type': content_type_id,
        'select': field_name
    })

    # Retrieve the text data from the fetched entries
    text = ""
    for entry in entries:
        if field_name in entry.fields:
            text += entry.fields[field_name]

    return text


def split_text(text):
    SENTENCE_ENDINGS = [".", "!", "?"]
    WORDS_BREAKS = [",", ";", ":", " ", "(", ")", "[", "]", "{", "}", "\t", "\n"]
    if args.verbose:
        print(f"Splitting text into sections")

    def find_sentence_start(start_index):
        sentence_start = start_index
        while sentence_start > 0 and text[sentence_start] not in SENTENCE_ENDINGS:
            if text[sentence_start] in WORDS_BREAKS:
                # If a word boundary is found within SENTENCE_SEARCH_LIMIT, use it as the start of the sentence
                return sentence_start + 1
            sentence_start -= 1
        return sentence_start

    all_text = text.strip()
    length = len(all_text)
    start = 0
    end = length
    while start + SECTION_OVERLAP < length:
        last_word = -1
        end = start + MAX_SECTION_LENGTH

        if end > length:
            end = length
        else:
            # Try to find the end of the sentence
            while end < length and (end - start - MAX_SECTION_LENGTH) < SENTENCE_SEARCH_LIMIT and all_text[
                end] not in SENTENCE_ENDINGS:
                if all_text[end] in WORDS_BREAKS:
                    last_word = end
                end += 1
            if end < length and all_text[end] not in SENTENCE_ENDINGS and last_word > 0:
                end = last_word  # Fall back to at least keeping a whole word
        if end < length:
            end += 1

        # Try to find the start of the sentence or at least a whole word boundary
        sentence_start = find_sentence_start(start)
        if sentence_start > 0:
            start = sentence_start

        section_text = all_text[start:end]
        yield section_text

        start = end - SECTION_OVERLAP

    if start + SECTION_OVERLAP < end:
        yield all_text[start:end]


def create_sections(text):
    sections = []
    for i, section_text in enumerate(split_text(text)):
        sections.append({
            "id": f"section-{i}",
            "content": section_text,
            "category": "",  # Add the appropriate category value if needed
            "sourcepage": "",  # Add the appropriate source page value if needed
            "sourcefile": ""  # Add the appropriate source file value if needed
        })
    return sections


def create_search_index():
    if args.verbose: print(f"Ensuring search index {args.index} exists")
    index_client = SearchIndexClient(endpoint=f"https://{args.searchservice}.search.windows.net/",
                                     credential=search_creds)
    if args.index not in index_client.list_index_names():
        index = SearchIndex(
            name=args.index,
            fields=[
                SimpleField(name="id", type="Edm.String", key=True),
                SearchableField(name="content", type="Edm.String", analyzer_name="en.microsoft"),
                SimpleField(name="category", type="Edm.String", filterable=True, facetable=True),
                SimpleField(name="sourcepage", type="Edm.String", filterable=True, facetable=True),
                SimpleField(name="sourcefile", type="Edm.String", filterable=True, facetable=True)
            ],
            semantic_settings=SemanticSettings(
                configurations=[SemanticConfiguration(
                    name='default',
                    prioritized_fields=PrioritizedFields(
                        title_field=None, prioritized_content_fields=[SemanticField(field_name='content')]))])
        )
        if args.verbose: print(f"Creating {args.index} search index")
        index_client.create_index(index)
    else:
        if args.verbose: print(f"Search index {args.index} already exists")


def index_sections(sections):
    search_client = SearchClient(
        endpoint=f"https://{args.searchservice}.search.windows.net/",
        index_name=args.index,
        credential=AzureKeyCredential(args.searchkey)
    )

    i = 0
    batch = []
    for section in sections:
        batch.append(section)
        i += 1
        if i % 1000 == 0:
            results = search_client.upload_documents(documents=batch)
            succeeded = sum([1 for r in results if r.succeeded])
            if args.verbose:
                print(f"\tIndexed {len(results)} sections, {succeeded} succeeded")
            batch = []

    if len(batch) > 0:
        results = search_client.upload_documents(documents=batch)
        succeeded = sum([1 for r in results if r.succeeded])
        if args.verbose:
            print(f"\tIndexed {len(results)} sections, {succeeded} succeeded")


def main():
    text = fetch_data_from_contentful()
    if args.verbose:
        print(f"Fetched data from Contentful:\n{text}")

    sections = create_sections(text)
    if args.verbose:
        print(f"Created {len(sections)} sections from the fetched data")

    create_search_index()
    if args.verbose:
        print(f"Ensured search index {args.index} exists")

    index_sections(sections)
    if args.verbose:
        print(f"Indexed {len(sections)} sections into search index {args.index}")


if __name__ == "__main__":
    main()
