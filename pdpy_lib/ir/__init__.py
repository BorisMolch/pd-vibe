"""
Pure Data IR (Intermediate Representation) System

This module provides semantic analysis and representation for Pure Data patches,
enabling cross-file symbol resolution, graph analysis, LLM-friendly DSL output,
and SQLite-based indexing.
"""

from .core import (
    IRPatch,
    IRPatchInfo,
    IRCanvas,
    IRNode,
    IREdge,
    IREdgeEndpoint,
    IRSymbol,
    IRSymbolEndpoint,
    IRAbstractionRef,
    IRExternalRef,
    IRSCC,
    IRInterface,
    IRInterfacePort,
    IRDiagnostic,
    IRDiagnostics,
    IREnrichment,
    IRNodeIO,
    IRIolet,
    IRLayout,
    IRAnalysis,
    NodeKind,
    EdgeKind,
    Domain,
    SymbolKind,
    SymbolNamespace,
)
from .build import IRBuilder, build_ir, build_ir_from_file
from .dsl import DSLSerializer, DSLMode, ir_to_dsl
from .ids import NodeIDGenerator, generate_canvas_path
from .symbols import SymbolExtractor, GlobalSymbolTable
from .registry import ObjectRegistry, ObjectSpec, get_registry
from .analysis import GraphAnalyzer
from .index import IRIndex, create_index, index_directory
from .enrich import EnrichmentData, EnrichmentCache, EnrichmentManager, enrich_ir
from .queries import (
    trace_to_dac,
    trace_from_adc,
    symbol_flow,
    find_feedback_paths,
    get_signal_chain,
    find_orphaned_connections,
    dependency_tree,
    find_similar_patterns,
    get_patch_summary,
    cross_patch_symbol_flow,
    find_all_abstractions,
    find_patches_using,
)

__all__ = [
    # Core types
    'IRPatch',
    'IRPatchInfo',
    'IRCanvas',
    'IRNode',
    'IREdge',
    'IREdgeEndpoint',
    'IRSymbol',
    'IRSymbolEndpoint',
    'IRAbstractionRef',
    'IRExternalRef',
    'IRSCC',
    'IRInterface',
    'IRInterfacePort',
    'IRDiagnostic',
    'IRDiagnostics',
    'IREnrichment',
    'IRNodeIO',
    'IRIolet',
    'IRLayout',
    'IRAnalysis',
    'NodeKind',
    'EdgeKind',
    'Domain',
    'SymbolKind',
    'SymbolNamespace',
    # Builder
    'IRBuilder',
    'build_ir',
    'build_ir_from_file',
    # DSL
    'DSLSerializer',
    'DSLMode',
    'ir_to_dsl',
    # IDs
    'NodeIDGenerator',
    'generate_canvas_path',
    # Symbols
    'SymbolExtractor',
    'GlobalSymbolTable',
    # Registry
    'ObjectRegistry',
    'ObjectSpec',
    'get_registry',
    # Analysis
    'GraphAnalyzer',
    # Index
    'IRIndex',
    'create_index',
    'index_directory',
    # Enrichment
    'EnrichmentData',
    'EnrichmentCache',
    'EnrichmentManager',
    'enrich_ir',
    # Queries
    'trace_to_dac',
    'trace_from_adc',
    'symbol_flow',
    'find_feedback_paths',
    'get_signal_chain',
    'find_orphaned_connections',
    'dependency_tree',
    'find_similar_patterns',
    'get_patch_summary',
    'cross_patch_symbol_flow',
    'find_all_abstractions',
    'find_patches_using',
]
