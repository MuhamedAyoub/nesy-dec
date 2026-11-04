#!/usr/bin/env ruby
# java_pipeline/teacher.rb — RoR-MSI's dual-objective clustering on a Java G and D.
#
# The Java counterpart of experiment_v2.rb's clustering half. G and D come from
# results/<app>/graph.json (java_pipeline/resolver.py) instead of the Ruby
# resolver; everything after loading is experiment_v2.rb's code path unchanged:
# the same isolated-class filter, ClusterEngine.get_microservices with the same
# arguments, the same per-cluster metrics, and the same JSON contract.
#
# Usage: ruby java_pipeline/teacher.rb GRAPH_JSON OUT_JSON [alpha] [beta] [n_top] [min_cluster_size] [gamma]
require_relative "../vendor/ror_msi/tools/ClassNode"
require_relative "../vendor/ror_msi/tools/MethodNode"
require_relative "../vendor/ror_msi/tools/ClassTypeEnum"
require_relative "../vendor/ror_msi/tools/helpers"
require_relative "../vendor/ror_msi/tools/DependencyAnalyzer"
require_relative "../vendor/ror_msi/tools/ClusterEngine"
require_relative "../vendor/ror_msi/tools/Cluster"
require 'json'
require 'set'
require 'tmpdir'

graph_file, output_file = ARGV[0], ARGV[1]
abort "usage: ruby java_pipeline/teacher.rb GRAPH_JSON OUT_JSON [alpha beta n_top min_cs gamma]" unless graph_file && output_file
alpha             = (ARGV[2] || 0.9).to_f
beta              = (ARGV[3] || 0.1).to_f
n_top             = (ARGV[4] || 8).to_i
min_cluster_size  = (ARGV[5] || 3).to_i
gamma             = (ARGV[6] || 0.1).to_f

g = JSON.parse(File.read(graph_file))
graph_in = g.fetch("dependency_graph")
data_in = g.fetch("data_associations")
entities = data_in.values.flatten.uniq

# --- isolated-class filtering (experiment_v2.rb lines 55-91) ---
isolated_classes = []
active_class_names = []
incoming = Set.new
graph_in.each { |src, deps| deps.each_key { |dst| incoming << dst unless dst == src } }
graph_in.each do |class_name, deps|
  non_self_out = deps.reject { |k, _| k == class_name }
  if non_self_out.empty? && !incoming.include?(class_name)
    isolated_classes << class_name
  else
    active_class_names << class_name
  end
end
active_set = Set.new(active_class_names)
filtered_graph = Hash.new { |h, k| h[k] = {} }
filtered_data  = Hash.new { |h, k| h[k] = [] }
graph_in.each do |src, edges|
  next unless active_set.include?(src)
  filtered_graph[src] = edges.select { |dst, _| active_set.include?(dst) }
end
active_class_names.each { |c| filtered_graph[c] }
data_in.each { |src, ents| filtered_data[src] = ents if active_set.include?(src) }
active_class_names.each { |c| filtered_data[c] }
deps = DependencyAnalyzer.allocate
deps.instance_variable_set(:@classNodes, [])
deps.instance_variable_set(:@dataNodes, [])
deps.instance_variable_set(:@graph, filtered_graph)
deps.instance_variable_set(:@data, filtered_data)
deps.instance_variable_set(:@data_count, Hash.new { |h, k| h[k] = {} })

$stderr.puts "[teacher] #{File.basename(File.dirname(graph_file))}: #{active_class_names.size} active, " \
             "#{isolated_classes.size} isolated, alpha=#{alpha} beta=#{beta}"

msa = Dir.mktmpdir do |tmp|
  ClusterEngine.get_microservices(deps, alpha, beta, File.join(tmp, "clusters"), n_top, min_cluster_size, gamma)
end

clusters, cluster_objects = [], []
if msa.is_a?(Array)
  msa.each_with_index do |cluster, idx|
    clusters << { "id" => idx + 1, "name" => cluster.name, "classes" => cluster.class_names }
    cluster_objects << cluster
  end
elsif msa.is_a?(Hash)
  msa.each_with_index do |(entity, class_list), idx|
    clusters << { "id" => idx + 1, "name" => "MS_#{entity}", "classes" => class_list }
    cluster_objects << Cluster.new("MS_#{entity}", class_list)
  end
end

cluster_metrics = cluster_objects.each_with_index.map do |cluster, idx|
  ca = deps.get_intra_dependencies_of_ms(cluster)
  ce = 0
  cluster.class_names.each do |cn|
    next unless deps.graph[cn]
    deps.graph[cn].each { |target, count| ce += count unless cluster.class_names.include?(target) }
  end
  f_struct = ca.to_f / (ce + ca + 1.0e-10)
  f_data = deps.get_data_cohesion_of_ms(cluster)
  { "cluster_id" => idx + 1, "num_classes" => cluster.class_names.size,
    "intra_dependencies" => ca.round(4), "inter_dependencies" => ce.round(4),
    "f_struct" => f_struct.round(6), "f_data" => f_data.round(6),
    "f_quality" => (alpha * f_struct + beta * f_data).round(6) }
end

result = {
  "parameters" => { "alpha" => alpha, "beta" => beta, "n_top" => n_top,
                    "min_cluster_size" => min_cluster_size, "gamma" => gamma,
                    "mode" => alpha > 0.3 ? "hierarchical" : "data_cohesion",
                    "resolver" => "java-layered", "graph" => graph_file },
  "summary" => { "total_classes_original" => graph_in.size, "total_classes_active" => active_class_names.size,
                 "isolated_classes" => isolated_classes.size, "total_data_entities" => entities.size,
                 "num_microservices" => clusters.size },
  "resolver_report" => g["resolver_report"],
  "dependency_graph" => deps.graph.transform_values(&:dup),
  "data_associations" => deps.data.transform_values(&:dup),
  "clusters" => clusters,
  "cluster_metrics" => cluster_metrics,
  "isolated_classes" => isolated_classes
}
File.write(output_file, JSON.pretty_generate(result))
$stderr.puts "[teacher] #{clusters.size} services -> #{output_file}"
