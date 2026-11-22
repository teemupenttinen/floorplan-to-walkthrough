using UnrealBuildTool;

// Runtime module of the walkthrough. Gameplay lives in C++ because Blueprint graphs cannot be written or
// edited from scripts; the scene itself is built by Content/Python/import_manifest.py.
public class Walkthrough : ModuleRules
{
	public Walkthrough(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] {
			"Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "Json", "JsonUtilities"
		});
	}
}
