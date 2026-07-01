# RAG module package initializer
# Applies global monkeypatches to resolve astrapy 1.5.2 compatibility with LlamaIndex.

import astrapy.exceptions
import astrapy.results

# LlamaIndex 0.6.0 AstraDB Vector Store expects these classes to exist in astrapy namespace
if not hasattr(astrapy.exceptions, "InsertManyException"):
    astrapy.exceptions.InsertManyException = astrapy.exceptions.CollectionInsertManyException

if not hasattr(astrapy.results, "UpdateResult"):
    astrapy.results.UpdateResult = astrapy.results.CollectionUpdateResult

if not hasattr(astrapy.results, "DeleteResult"):
    astrapy.results.DeleteResult = astrapy.results.CollectionDeleteResult
